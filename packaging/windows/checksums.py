"""Escribe `SHA256SUMS.txt` con el formato de `sha256sum`: `<sha256>  <nombre>`."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def write_checksums(paths: list[Path], out: Path) -> None:
    lines = []
    for path in sorted(paths, key=lambda p: p.name):
        digest = hashlib.sha256()
        with path.open("rb") as handle:  # FileNotFoundError si falta: no se publica a medias
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.name}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    *files, target = sys.argv[1:]
    write_checksums([Path(f) for f in files], Path(target))
