#!/usr/bin/env python3
"""Write a deterministic SHA256 manifest for the public staging tree."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "PUBLIC_RELEASE_MANIFEST.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    files = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT or ".git" in path.parts:
            continue
        files[str(path.relative_to(ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
    OUTPUT.write_text(json.dumps({"schema": "public-release-manifest.v1", "files": files}, indent=2) + "\n")
    print(f"wrote {len(files)} file entries to {OUTPUT}")


if __name__ == "__main__":
    main()
