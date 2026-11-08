"""Notificaciones de `osineitor watch`: webhook, correo SMTP y fichero NDJSON.

Un fallo al avisar no tumba la vigilancia: se devuelve en la lista de entregas. Las URLs de webhook
y las contraseñas son secretos: nunca salen en un mensaje de error.
"""

from __future__ import annotations

import asyncio
import json
import os
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING, Any

from osineitor import logs
from osineitor.config import Config
from osineitor.http import HttpClient

if TYPE_CHECKING:
    from osineitor.watch import Alert, Notifier

MAX_LISTED = 20  # alertas que se escriben en un mensaje; el resto se resume
DISCORD_LIMIT = 1900
SMTP_TIMEOUT = 30
WEBHOOK_TIMEOUT_NOTE = "sin respuesta"


class NotifyError(Exception):
    """No se pudo entregar el aviso. El mensaje no contiene secretos."""


def _rank(severity: str) -> int:
    from osineitor.watch import severity_rank

    return severity_rank(severity)


def message(target: str, alerts: list[Alert]) -> str:
    """Texto plano del aviso: un resumen y una línea por alerta, de más a menos grave."""
    ordered = sorted(alerts, key=lambda a: -_rank(a.severity))
    counts: dict[str, int] = {}
    for a in ordered:
        counts[a.severity] = counts.get(a.severity, 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in counts.items())
    lines = [f"OSINEITOR · {target}: {len(alerts)} alerta(s) nueva(s) ({summary})"]
    lines += [f"- [{a.severity}] {a.title}: {a.value}" for a in ordered[:MAX_LISTED]]
    if len(ordered) > MAX_LISTED:
        lines.append(f"… y {len(ordered) - MAX_LISTED} más")
    return "\n".join(lines)


def _secret(options: dict[str, Any], key: str) -> str:
    """Valor directo (`key`) o leído de la variable de entorno que indica `key_env`."""
    if value := options.get(key):
        return str(value)
    name = options.get(f"{key}_env")
    if name and (value := os.environ.get(str(name))):
        return value
    raise NotifyError(f"falta {key}: la variable de entorno {name!r} no está definida")


def payload(fmt: str, target: str, scan_id: int | None, alerts: list[Alert]) -> dict[str, Any]:
    text = message(target, alerts)
    # Los valores son de terceros: un `@everyone` o `<!channel>` no debe avisar a todo el canal.
    if fmt == "discord":
        return {"content": text[:DISCORD_LIMIT], "allowed_mentions": {"parse": []}}
    if fmt == "slack":  # Slack interpreta `<…>` como mención o enlace; así se pide escaparlo
        return {"text": text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}
    if fmt == "teams":
        return {"text": text}
    return {
        "text": text,
        "target": target,
        "scan_id": scan_id,
        "alerts": [a.as_dict() for a in alerts],
    }


async def _webhook(
    notifier: Notifier, target: str, scan_id: int | None, alerts: list[Alert]
) -> None:
    url = _secret(notifier.options, "url")
    if not url.startswith(("https://", "http://")):
        raise NotifyError("la URL del webhook debe empezar por https:// o http://")
    # El token va en la ruta (Slack, Discord, Teams), y la ruta sí llega al registro.
    logs.mask_secret(url)
    logs.mask_secret(logs.redact_url(url))
    body = payload(notifier.options.get("format", "generic"), target, scan_id, alerts)
    private = bool(notifier.options.get("allow_private", False))
    async with HttpClient(Config.load(), allow_private=private, retries=1) as http:
        try:
            response = await http.post(url, json=body)
        except Exception as exc:  # el texto de la excepción puede llevar la URL
            raise NotifyError(f"no se pudo conectar ({type(exc).__name__})") from None
    if response.status_code >= 300:
        raise NotifyError(f"el webhook respondió HTTP {response.status_code}")


def _send_mail(notifier: Notifier, subject: str, text: str) -> None:
    opts = notifier.options
    if opts.get("username") and not opts.get("ssl") and not opts.get("starttls", True):
        raise NotifyError(
            "con `username`, SMTP necesita `ssl` o `starttls`: la contraseña iría en claro"
        )
    msg = EmailMessage()
    msg["Subject"] = " ".join(subject.split())  # sin saltos de línea: no se inyectan cabeceras
    msg["From"] = opts["from"]
    msg["To"] = ", ".join(opts["to"])
    msg.set_content(text)
    host, port = opts["host"], int(opts.get("port", 465 if opts.get("ssl") else 587))
    smtp: smtplib.SMTP = (
        smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=ssl.create_default_context())
        if opts.get("ssl")
        else smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    )
    with smtp:
        if opts.get("starttls", True) and not opts.get("ssl"):
            smtp.starttls(context=ssl.create_default_context())
        if opts.get("username"):
            smtp.login(str(opts["username"]), _secret(opts, "password"))
        smtp.send_message(msg)


async def _email(notifier: Notifier, target: str, scan_id: int | None, alerts: list[Alert]) -> None:
    subject = f"OSINEITOR: {len(alerts)} alerta(s) nueva(s) en {target}"
    try:
        await asyncio.to_thread(_send_mail, notifier, subject, message(target, alerts))
    except NotifyError:
        raise
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        raise NotifyError(f"fallo SMTP ({type(exc).__name__})") from None


async def _file(notifier: Notifier, target: str, scan_id: int | None, alerts: list[Alert]) -> None:
    """Una línea JSON por alerta: lo recogen Filebeat, Telegraf, Promtail y similares."""
    path = Path(str(notifier.options["path"])).expanduser()
    at = datetime.now(UTC).isoformat()
    lines = [
        json.dumps(
            {"ts": at, "target": target, "scan_id": scan_id, **a.as_dict()},
            ensure_ascii=False,
            default=str,
        )
        for a in alerts
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
    except OSError as exc:
        raise NotifyError(f"no se puede escribir en el fichero ({exc.strerror or exc})") from None


SENDERS = {"webhook": _webhook, "email": _email, "file": _file}


async def deliver(
    notifiers: list[Notifier], target: str, scan_id: int | None, alerts: list[Alert]
) -> list[dict[str, Any]]:
    """Avisa por cada notificador de las alertas que alcanzan su `min_severity`."""
    out: list[dict[str, Any]] = []
    for notifier in notifiers:
        wanted = [a for a in alerts if _rank(a.severity) >= _rank(notifier.min_severity)]
        if not wanted:
            out.append({"notifier": notifier.name, "ok": True, "sent": 0, "error": None})
            continue
        try:
            await SENDERS[notifier.type](notifier, target, scan_id, wanted)
            out.append({"notifier": notifier.name, "ok": True, "sent": len(wanted), "error": None})
        except NotifyError as exc:
            out.append({"notifier": notifier.name, "ok": False, "sent": 0, "error": str(exc)})
    return out
