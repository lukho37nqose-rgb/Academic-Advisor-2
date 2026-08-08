"""Stable identifiers for cross-surface decision lineage."""

from __future__ import annotations

import hashlib


def stable_information_reference(
    *,
    tenant_id: str,
    domain_id: str,
    subject_id: str,
    fact_id: str,
) -> str:
    """Return an opaque subject-safe reference for an accepted fact lineage."""

    material = "\0".join([tenant_id, domain_id, subject_id, fact_id])
    return "info_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
