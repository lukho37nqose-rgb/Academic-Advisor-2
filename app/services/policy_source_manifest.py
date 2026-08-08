"""Canonical source manifest for signed policy releases."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class PolicySourceManifestError(ValueError):
    """A policy release does not preserve enough source provenance."""


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_POLICY_SOURCE_FIELDS = {
    "source_id",
    "source_version",
    "source_title",
    "document_hash",
    "page_start",
    "page_end",
    "section",
    "rule_identifier",
    "effective_from",
    "effective_until",
    "display_title",
    "source_anchor",
    "excerpt_reference",
}


def _policy_source_reference(node: dict[str, Any]) -> dict[str, Any] | None:
    raw = node.get("policy_source") or node.get("policy_source_reference")
    if not isinstance(raw, dict):
        return None
    reference = {key: raw[key] for key in sorted(_POLICY_SOURCE_FIELDS) if raw.get(key) is not None}
    return reference or None


def _walk_rule_sources(node: dict[str, Any], entries: list[dict[str, Any]], missing: list[str]) -> None:
    label = str(node.get("label") or node.get("id") or "Unnamed rule").strip()
    if "operator" in node:
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk_rule_sources(child, entries, missing)
        return

    citation = str(node.get("source_citation") or "").strip()
    if not citation:
        missing.append(label)
        return
    entry: dict[str, Any] = {
        "rule_id": str(node.get("id") or "").strip(),
        "label": label,
        "target": str(node.get("target") or "").strip(),
        "condition": str(node.get("condition") or "").strip(),
        "source_citation": citation,
    }
    reference = _policy_source_reference(node)
    if reference is not None:
        entry["policy_source"] = reference
    entries.append(entry)


def build_policy_source_manifest(policy_payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return a canonical source manifest and SHA-256 hash for a policy payload.

    The manifest binds release rules to their cited institutional sources. It
    does not prove that the institution's interpretation is correct; it proves
    that the signed release was approved with a stable citation structure.
    """
    root = policy_payload.get("root")
    if not isinstance(root, dict):
        raise PolicySourceManifestError("Policy payload must contain a root object.")

    entries: list[dict[str, str]] = []
    missing: list[str] = []
    _walk_rule_sources(root, entries, missing)
    if missing:
        names = ", ".join(sorted(set(missing))[:8])
        raise PolicySourceManifestError(
            f"Every release rule must include a source citation before publication. Missing: {names}."
        )
    if not entries:
        raise PolicySourceManifestError("A release must contain at least one cited rule source.")

    manifest = {
        "format_version": "1.0",
        "entries": sorted(entries, key=lambda item: (item["target"], item["rule_id"], item["source_citation"])),
    }
    return manifest, _stable_hash(manifest)
