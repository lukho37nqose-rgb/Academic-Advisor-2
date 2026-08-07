"""Repository-level architecture guardrails for Cacisa."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "app" / "core"
OPERATING_MODEL = REPO_ROOT / "docs" / "CODEX_OPERATING_MODEL.md"
AGENTS = REPO_ROOT / "AGENTS.md"


INSTITUTION_SPECIFIC_TERMS = re.compile(
    r"\b("
    r"uct|humanities|demo_university|demo_foundation|"
    r"curriculum_2026|grant_eligibility_2024|"
    r"student|course|faculty|credit|grant"
    r")\b",
    re.IGNORECASE,
)


def test_core_does_not_encode_institution_specific_policy_terms() -> None:
    offenders: list[str] = []

    for path in sorted(CORE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if match := INSTITUTION_SPECIFIC_TERMS.search(text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)}")

    assert not offenders, (
        "app/core must stay domain-neutral; move institution-specific policy "
        "language to edge configuration, services, adapters, docs, or frontend. "
        f"Found: {', '.join(offenders)}"
    )


def test_codex_operating_model_is_discoverable() -> None:
    assert AGENTS.exists()
    agents_text = AGENTS.read_text(encoding="utf-8")
    operating_text = OPERATING_MODEL.read_text(encoding="utf-8")

    assert "docs/CODEX_OPERATING_MODEL.md" in agents_text
    assert "Evidence -> candidate fact proposal" in operating_text
    assert "cacisa-verification-auditor" in operating_text
