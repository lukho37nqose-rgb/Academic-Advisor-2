from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_are_hash_locked_and_match_the_sbom(tmp_path: Path) -> None:
    lock = ROOT / "requirements.txt"
    committed_sbom = ROOT / "sbom.cdx.json"
    generated_sbom = tmp_path / "sbom.cdx.json"

    subprocess.run(
        [
            sys.executable,
            "tools/generate_sbom.py",
            "--requirements",
            str(lock),
            "--output",
            str(generated_sbom),
        ],
        cwd=ROOT,
        check=True,
    )

    lock_text = lock.read_text(encoding="utf-8")
    assert "--only-binary=:all:" in lock_text
    assert "--hash=sha256:" in lock_text
    assert generated_sbom.read_bytes() == committed_sbom.read_bytes()

    sbom = json.loads(committed_sbom.read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["components"]
