"""Generate a deterministic CycloneDX SBOM from the hash-locked requirements file."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib.parse import quote


PACKAGE_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)")
HASH_PATTERN = re.compile(r"^--hash=sha256:([a-f0-9]{64})$")


def parse_lock(requirements: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().rstrip("\\").strip()
        if not line or line.startswith("#") or line.startswith("--") and not line.startswith("--hash"):
            continue
        package_match = PACKAGE_PATTERN.match(line)
        if package_match:
            current = {
                "name": package_match.group(1),
                "version": package_match.group(2),
                "hashes": [],
            }
            components.append(current)
            continue
        hash_match = HASH_PATTERN.match(line)
        if hash_match and current is not None:
            hashes = current["hashes"]
            if isinstance(hashes, list):
                hashes.append(hash_match.group(1))
            continue
        raise RuntimeError(f"Unable to parse locked requirement line: {raw_line}")
    if not components or any(not component["hashes"] for component in components):
        raise RuntimeError("Every locked dependency must have at least one SHA-256 hash.")
    return components


def build_sbom(requirements: Path) -> dict[str, object]:
    lock_text = requirements.read_text(encoding="utf-8").replace("\r\n", "\n")
    lock_digest = hashlib.sha256(lock_text.encode("utf-8")).hexdigest()
    components = []
    for component in parse_lock(requirements):
        name = str(component["name"])
        version = str(component["version"])
        hash_values = component["hashes"]
        if not isinstance(hash_values, list) or not all(isinstance(value, str) for value in hash_values):
            raise RuntimeError("Locked dependency hashes must be strings.")
        hashes = [str(value) for value in hash_values]
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{quote(name)}@{quote(version)}",
                "hashes": [{"alg": "SHA-256", "content": digest} for digest in hashes],
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, lock_digest)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "institutional-reasoning-engine",
                "version": lock_digest[:12],
                "properties": [
                    {"name": "ire:requirements-lock-sha256", "value": lock_digest},
                    {"name": "ire:python-runtime", "value": "CPython 3.12"},
                ],
            }
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--output", type=Path, default=Path("sbom.cdx.json"))
    arguments = parser.parse_args()
    arguments.output.write_text(
        json.dumps(build_sbom(arguments.requirements), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
