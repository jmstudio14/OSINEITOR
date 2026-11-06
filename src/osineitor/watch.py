"""Vigilancia continua: repite scans de unos objetivos y avisa solo de lo que cambió.

El fichero `watch.yml` (por defecto en la carpeta de configuración) declara qué vigilar y adónde
avisar. Se ejecuta con `osineitor watch run` desde cron, systemd o GitHub Actions; ver
`docs/VIGILANCIA.md`.

    notifiers:
      slack:
        type: webhook               # webhook | email | file
        url_env: OSINEITOR_SLACK_URL
        format: slack               # generic | slack | discord | teams
        min_severity: medium
    targets:
      - target: example.com
        preset: domain-recon        # opcional; también depth, modules, active
        every: 1d                   # cada cuánto toca ejecutarlo (30m, 6h, 1d)
        notify: [slack]             # por defecto, todos

Qué es «nuevo»: una entidad cuya clave no figura entre las que la vigilancia de ese objetivo ya
conoce. La primera ejecución solo fija esa línea base y no alerta. Si una entidad desaparece en
un scan completo y sin errores de módulos, se olvida: si vuelve a aparecer, alerta otra vez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from osineitor import presets
from osineitor.errors import InvalidEntityValue
from osineitor.findings import SEVERITIES, evaluate, load_rules
from osineitor.models import Entity, EntityType, ScanResult, detect_type
from osineitor.scanner import ScanInputError, Scanner
from osineitor.storage import Storage

ALERT_RULES_FILE = Path(__file__).parent / "data" / "rules" / "alerts.yml"
NOTIFIER_TYPES = ("webhook", "email", "file")
WEBHOOK_FORMATS = ("generic", "slack", "discord", "teams")
TARGET_KEYS = {"target", "type", "preset", "depth", "modules", "active", "every", "notify"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
EVERY_RE = re.compile(r"^(\d+)([mhd])$")
UNITS = {"m": "minutes", "h": "hours", "d": "days"}
MIN_EVERY = timedelta(minutes=5)


class WatchError(ValueError):
    """El fichero de vigilancia no es válido."""


@dataclass(frozen=True)
class Notifier:
    name: str
    type: str
    options: dict[str, Any]

    @property
    def min_severity(self) -> str:
        return self.options.get("min_severity", "info")


@dataclass(frozen=True)
class Target:
    target: str
    type: EntityType
    key: str  # clave canónica de la semilla (`domain:example.com`); identifica el estado guardado
    every: timedelta
    preset: str | None = None
    depth: int | None = None
    modules: tuple[str, ...] | None = None
    active: bool = False
    notify: tuple[str, ...] | None = None  # None: todos


@dataclass(frozen=True)
class WatchConfig:
    targets: tuple[Target, ...]
    notifiers: dict[str, Notifier] = field(default_factory=dict)


@dataclass(frozen=True)
class Alert:
    rule: str
    title: str
    severity: str
    entity: str  # clave de la entidad nueva que la provocó
    value: str
    recommendation: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "title": self.title,
            "severity": self.severity,
            "entity": self.entity,
            "value": self.value,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
        }


@dataclass
class TargetReport:
    target: str
    due: bool
    ran: bool = False
    scan_id: int | None = None
    status: str | None = None
    baseline: bool = False
    alerts: list[Alert] = field(default_factory=list)
    deliveries: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "due": self.due,
            "ran": self.ran,
            "scan_id": self.scan_id,
            "status": self.status,
            "baseline": self.baseline,
            "alerts": [a.as_dict() for a in self.alerts],
            "deliveries": self.deliveries,
            "error": self.error,
        }


def default_file() -> Path:
    from osineitor.config import config_dir

    return config_dir() / "watch.yml"


def parse_every(text: Any) -> timedelta:
    match = EVERY_RE.fullmatch(str(text).strip().lower())
    if not match:
        raise WatchError(f"`every` debe ser un número y m, h o d (p. ej. 6h): {text!r}")
    value = timedelta(**{UNITS[match[2]]: int(match[1])})
    if value < MIN_EVERY:
        raise WatchError("`every` no puede ser menor de 5 minutos")
    return value


def _notifier(name: str, raw: Any) -> Notifier:
    if not NAME_RE.fullmatch(str(name)):
        raise WatchError(f"nombre de notificador no válido: {name!r}")
    if not isinstance(raw, dict) or raw.get("type") not in NOTIFIER_TYPES:
        raise WatchError(f"{name}: `type` debe ser {', '.join(NOTIFIER_TYPES)}")
    options = {k: v for k, v in raw.items() if k != "type"}
    if options.get("min_severity", "info") not in SEVERITIES:
        raise WatchError(f"{name}: `min_severity` debe ser {', '.join(SEVERITIES)}")
    kind = raw["type"]
    if kind == "webhook":
        if not (bool(options.get("url")) ^ bool(options.get("url_env"))):
            raise WatchError(f"{name}: indica `url` o `url_env`, no ambos ni ninguno")
        if options.get("format", "generic") not in WEBHOOK_FORMATS:
            raise WatchError(f"{name}: `format` debe ser {', '.join(WEBHOOK_FORMATS)}")
    elif kind == "email":
        for key in ("host", "from", "to"):
            if not options.get(key):
                raise WatchError(f"{name}: falta `{key}`")
        if isinstance(options["to"], str):
            options["to"] = [options["to"]]
        if not all(isinstance(a, str) and a for a in options["to"]):
            raise WatchError(f"{name}: `to` debe ser una dirección o una lista de ellas")
        if options.get("starttls") and options.get("ssl"):
            raise WatchError(f"{name}: `starttls` y `ssl` son excluyentes")
    elif not options.get("path"):
        raise WatchError(f"{name}: falta `path`")
    return Notifier(str(name), kind, options)


def _target(raw: Any, notifiers: dict[str, Notifier]) -> Target:
    if not isinstance(raw, dict) or not raw.get("target"):
        raise WatchError("cada objetivo necesita `target`")
    if unknown := set(raw) - TARGET_KEYS:
        raise WatchError(f"{raw['target']}: claves desconocidas: {', '.join(sorted(unknown))}")
    value = str(raw["target"]).strip()
    try:
        kind = EntityType(raw["type"]) if raw.get("type") else detect_type(value)
    except (ValueError, InvalidEntityValue) as exc:
        raise WatchError(f"{value}: {exc}") from exc
    try:
        key = Entity(type=kind, value=value).key
    except ValueError as exc:  # pydantic ValidationError e InvalidEntityValue lo son
        raise WatchError(f"{value}: {str(exc).splitlines()[-1] if str(exc) else exc}") from exc
    depth = raw.get("depth")
    if depth is not None and not (type(depth) is int and 1 <= depth <= 4):
        raise WatchError(f"{value}: `depth` debe ser un entero de 1 a 4")
    modules = raw.get("modules")
    if modules is not None and not (
        isinstance(modules, list) and modules and all(isinstance(m, str) for m in modules)
    ):
        raise WatchError(f"{value}: `modules` debe ser una lista no vacía de nombres")
    if not isinstance(raw.get("active", False), bool):
        raise WatchError(f"{value}: `active` debe ser true o false")
    notify = raw.get("notify")
    if notify is not None:
        if not (isinstance(notify, list) and all(isinstance(n, str) for n in notify)):
            raise WatchError(f"{value}: `notify` debe ser una lista de notificadores")
        if missing := [n for n in notify if n not in notifiers]:
            raise WatchError(f"{value}: notificador desconocido: {', '.join(missing)}")
    return Target(
        target=value,
        type=kind,
        key=key,
        every=parse_every(raw.get("every", "1d")),
        preset=raw.get("preset"),
        depth=depth,
        modules=tuple(modules) if modules else None,
        active=raw.get("active", False),
        notify=tuple(notify) if notify is not None else None,
    )


def load_config(path: Path) -> WatchConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WatchError(f"no se puede leer {path}: {exc.strerror or exc}") from exc
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise WatchError(f"{path}: no es un YAML válido ({exc})") from exc
    if not isinstance(raw, dict) or not raw.get("targets"):
        raise WatchError(f"{path}: debe tener una lista `targets`")
    if unknown := set(raw) - {"targets", "notifiers"}:
        raise WatchError(f"{path}: claves desconocidas: {', '.join(sorted(map(str, unknown)))}")
    notifiers_raw = raw.get("notifiers") or {}
    if not isinstance(notifiers_raw, dict) or not isinstance(raw["targets"], list):
        raise WatchError(f"{path}: `notifiers` es un mapa y `targets`, una lista")
    notifiers = {str(n): _notifier(n, body) for n, body in notifiers_raw.items()}
    targets = tuple(_target(item, notifiers) for item in raw["targets"])
    seen = [t.key for t in targets]
    if len(seen) != len(set(seen)):
        raise WatchError(f"{path}: hay objetivos repetidos")
    return WatchConfig(targets=targets, notifiers=notifiers)


def is_due(last_at: str | None, every: timedelta, now: datetime) -> bool:
    """Toca ejecutar si pasó el intervalo. Un cron cada hora no debe retrasar un `1d` un día
    entero por unos segundos de diferencia: se admite una holgura del 10 % (máximo 10 minutos)."""
    if last_at is None:
        return True
    slack = min(every / 10, timedelta(minutes=10))
    return now - datetime.fromisoformat(last_at) >= every - slack


def find_alerts(result: ScanResult, known: set[str]) -> tuple[list[Alert], set[str]]:
    """Alertas de lo que `known` aún no conoce, y las claves de esas entidades nuevas."""
    rules = load_rules(ALERT_RULES_FILE)
    fresh = [e for e in result.entities if e.key not in known and e.key != result.target.key]
    alerts: list[Alert] = []
    for entity in fresh:
        if entity.type == EntityType.FINDING:
            alerts.append(
                Alert(
                    rule=str(entity.data.get("rule", "finding")),
                    title=str(entity.data.get("title", entity.value)),
                    severity=str(entity.data.get("severity", "info")),
                    entity=entity.key,
                    value=entity.value,
                    recommendation=str(entity.data.get("recommendation", "")),
                    evidence=entity.data.get("evidence") or {},
                )
            )
            continue
        alerts += [
            Alert(
                rule=m.rule.id,
                title=m.rule.title,
                severity=m.rule.severity,
                entity=entity.key,
                value=entity.value,
                recommendation=m.rule.recommendation,
                evidence=m.evidence,
            )
            for m in evaluate(rules, entity)
        ]
    return alerts, {e.key for e in fresh}


def _scanner(target: Target) -> Scanner:
    depth, modules = target.depth, target.modules
    options: dict[str, Any] = {}
    if target.preset:
        try:
            preset = presets.get(target.preset)
        except presets.PresetError as exc:
            raise ScanInputError(str(exc)) from exc
        if target.active and not preset.allow_active:
            raise ScanInputError(f"el preset {target.preset} no admite módulos activos")
        depth = depth or preset.depth
        modules = modules or preset.modules
        # En el preset, 0 significa sin límite; en `Scanner`, None.
        for name, value in (
            ("max_entities", preset.max_entities),
            ("max_requests", preset.max_requests),
            ("max_seconds", preset.max_time),
        ):
            if value is not None:
                options[name] = value or None
    return Scanner(depth=depth or 1, only=modules, active=target.active, **options)


def _clean(result: ScanResult) -> bool:
    """Un scan completo y sin fallos de módulos: sirve para dar por desaparecido lo que falta."""
    return result.status == "complete" and not any(
        run.status in ("error", "quota") for run in result.runs
    )


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else 0


async def run_target(
    target: Target,
    config: WatchConfig,
    storage: Storage,
    now: datetime,
    *,
    force: bool = False,
) -> TargetReport:
    from osineitor import notify

    last = storage.watch_last(target.key)
    due = force or is_due(last[0] if last else None, target.every, now)
    report = TargetReport(target=target.target, due=due)
    if not report.due:
        return report
    try:
        result = await _scanner(target).ascan(target.target, target.type)
    except ScanInputError as exc:
        report.error = str(exc)
        return report
    except Exception as exc:  # un objetivo que falla no debe impedir vigilar los demás
        report.error = f"{type(exc).__name__}: {exc}"
        return report
    report.ran = True
    report.status = result.status
    report.scan_id = storage.save(result)
    known = storage.watch_seen(target.key)
    report.baseline = last is None
    alerts, fresh = find_alerts(result, known)
    keep_out: set[str] = set()
    if not report.baseline and alerts:
        report.alerts = alerts
        names = target.notify if target.notify is not None else tuple(config.notifiers)
        batch = [config.notifiers[n] for n in names]
        report.deliveries = await notify.deliver(batch, target.target, report.scan_id, alerts)
        if report.deliveries and not any(d["ok"] for d in report.deliveries):
            # Nadie recibió el aviso: que se repita en la próxima ejecución en lugar de perderse.
            keep_out = {a.entity for a in alerts}
    gone = known - {e.key for e in result.entities} if _clean(result) else set()
    storage.watch_record(
        target.key,
        at=now.astimezone(UTC).isoformat(),
        scan_id=report.scan_id,
        status=result.status,
        add=fresh - keep_out,
        remove=gone,
    )
    return report


async def run_watch(
    config: WatchConfig,
    storage: Storage,
    *,
    only: list[str] | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> list[TargetReport]:
    """Ejecuta los objetivos que tocan, uno tras otro (cada scan ya es concurrente por dentro)."""
    now = now or datetime.now(UTC)
    wanted = [
        t for t in config.targets if not only or t.target.lower() in {o.lower() for o in only}
    ]
    if only and (missing := {o.lower() for o in only} - {t.target.lower() for t in wanted}):
        raise WatchError(f"objetivos no declarados en el fichero: {', '.join(sorted(missing))}")
    return [await run_target(t, config, storage, now, force=force) for t in wanted]
