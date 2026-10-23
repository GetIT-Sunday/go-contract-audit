#!/usr/bin/env python3
"""Small deterministic checks for the files included in the public staging tree."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    capsule = ROOT / "examples" / "diagnosis_capsule"
    with tempfile.TemporaryDirectory(prefix="goaudit-release-") as tmp:
        result = Path(tmp) / "capsule.json"
        subprocess.run(
            [sys.executable, str(capsule / "audit_examples.py"), "audit", "--out", str(result)],
            cwd=capsule, check=True,
        )
        subprocess.run(
            [sys.executable, str(capsule / "audit_examples.py"), "check", "--out", str(result)],
            cwd=capsule, check=True,
        )
    required = [
        ROOT / "README.md",
        ROOT / "pyproject.toml",
        ROOT / "requirements.txt",
        ROOT / "paper" / "main.tex",
        ROOT / "paper" / "references.bib",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing required release files: " + ", ".join(missing))
    print(json.dumps({"status": "PASS", "root": str(ROOT), "required_files": len(required)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
