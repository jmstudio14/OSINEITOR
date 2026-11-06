"""F10.6: mide cuántas afirmaciones sin respaldo deja pasar el validador de citas.

Sin argumentos evalúa el validador con un corpus etiquetado (`tests/ai_eval/corpus.json`): un scan
de ejemplo y frases que respaldan o no los hechos, cada una con su tipo de defecto. Con `--live`
envía el scan de ejemplo al modelo configurado en `ai.yml` y cuenta qué parte de sus frases
descarta el validador (los datos del corpus no son reales, pero la petición sale al proveedor:
con uno remoto exige `consent_remote` como siempre).

    python scripts/eval_ai.py [--live] [--config ai.yml] [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from osineitor import ai
from osineitor.models import ScanResult

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "ai_eval" / "corpus.json"
STRUCTURAL = ("no_citation", "bad_citation", "invented_literal")


def load_corpus(path: Path = CORPUS) -> tuple[ScanResult, dict[str, str], list[dict]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ScanResult.model_validate(raw["scan"]), raw["aliases"], raw["sentences"]


def resolve(text: str, aliases: dict[str, str], ids: dict[str, str]) -> str:
    """Cambia `{alias}` por la cita `[E#]` de la entidad que nombra el alias."""
    for alias, key in aliases.items():
        text = text.replace("{" + alias + "}", f"[{ids[key]}]")
    return text


def evaluate(path: Path = CORPUS) -> dict:
    scan, aliases, sentences = load_corpus(path)
    facts, _ = ai.build_facts(scan)
    ids = {fact.key: fact.id for fact in facts}
    kinds: dict[str, dict[str, int]] = {}
    accepted = accepted_unsupported = false_rejects = 0
    for item in sentences:
        passed = bool(ai.validate(resolve(item["text"], aliases, ids), facts)[0])
        slot = kinds.setdefault(item["kind"], {"total": 0, "rejected": 0})
        slot["total"] += 1
        slot["rejected"] += not passed
        accepted += passed
        accepted_unsupported += passed and not item["supported"]
        false_rejects += (not passed) and item["supported"]
    supported = sum(1 for s in sentences if s["supported"])
    return {
        "sentences": len(sentences),
        "supported": supported,
        "unsupported": len(sentences) - supported,
        "accepted": accepted,
        "accepted_unsupported": accepted_unsupported,
        "false_rejects": false_rejects,
        "kinds": kinds,
    }


async def live(config_path: Path | None, path: Path = CORPUS) -> dict:
    config = ai.load_config(config_path or ai.default_file())
    scan, _, _ = load_corpus(path)
    facts, omitted = ai.build_facts(scan)
    reply = await ai.complete(config, ai.SYSTEM, ai.build_prompt(scan, facts, omitted))
    accepted, rejected = ai.validate(reply, facts)
    total = len(accepted) + len(rejected)
    return {
        "provider": config.provider,
        "model": config.model,
        "sentences": total,
        "rejected": len(rejected),
        "rejected_rate": len(rejected) / total if total else 0.0,
        "reasons": [s.reason for s in rejected],
    }


def structural(report: dict) -> tuple[int, int]:
    """(rechazadas, total) de las frases con un defecto que el validador puede ver."""
    slots = [report["kinds"].get(kind, {"total": 0, "rejected": 0}) for kind in STRUCTURAL]
    return sum(s["rejected"] for s in slots), sum(s["total"] for s in slots)


def render(report: dict) -> str:
    caught, total = structural(report)
    lines = [
        f"Frases del corpus: {report['sentences']} "
        f"({report['supported']} respaldadas, {report['unsupported']} sin respaldo)",
        f"Sin respaldo con defecto estructural, rechazadas: {caught} de {total}",
        f"Respaldadas rechazadas por error: {report['false_rejects']} de {report['supported']}",
        f"Sin respaldo que pasan el validador: {report['accepted_unsupported']} de "
        f"{report['accepted']} aceptadas",
    ]
    lines += [
        f"  {kind}: {slot['rejected']} de {slot['total']} rechazadas"
        for kind, slot in report["kinds"].items()
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="evalúa el modelo de ai.yml")
    parser.add_argument("--config", type=Path, help="fichero ai.yml (con --live)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(live(args.config)) if args.live else evaluate()
    except ai.AiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.live:
        print(
            f"{report['provider']}/{report['model']}: {report['rejected']} de "
            f"{report['sentences']} frases descartadas ({report['rejected_rate']:.0%})"
        )
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
