"""Release-bundle verification used before a production evaluation runs."""

import os
from typing import Any

from app.core.compiler import compile_release_to_graph
from app.core.crypto import CryptoService
from app.core.models import Release, RuleGraph


class ReleaseIntegrityError(ValueError):
    """A persisted release no longer proves the policy it claims to execute."""


def _iso_date(value: object) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def verify_release_bundle(
    release: Release,
    compiled_rule_graph: RuleGraph | None = None,
) -> tuple[bool, str]:
    """Verify the stored signing bundle and its binding to persisted release data.

    The signed policy is recompiled when a compiled graph is supplied. That
    catches an altered graph even if the release row and signature fields have
    not changed. Legacy releases are intentionally identifiable rather than
    silently treated as cryptographically verified.
    """
    if not (
        release.signed_payload
        and release.signed_payload_hash
        and release.signing_key_id
        and release.signing_public_key
        and release.digital_signature
    ):
        return False, "release has no complete signing verification bundle"

    signed_release = release.signed_payload.get("release")
    signed_policy = release.signed_payload.get("policy")
    if not isinstance(signed_release, dict) or not isinstance(signed_policy, dict):
        return False, "signed payload has no release and policy objects"

    expected_release: dict[str, Any] = {
        "id": release.id,
        "domain_id": release.domain_id,
        "version": release.version,
        "rule_graph_id": release.rule_graph_id,
        "effective_from": _iso_date(release.effective_from),
        "effective_until": _iso_date(release.effective_until),
        "applicability": release.applicability,
    }
    if signed_release != expected_release:
        return False, "persisted release metadata differs from its signed payload"

    if not CryptoService.verify_signed_payload(
        payload=release.signed_payload,
        signature_hex=release.digital_signature,
        expected_hash=release.signed_payload_hash,
        public_key_pem=release.signing_public_key,
    ):
        return False, "release signature verification failed"

    if compiled_rule_graph is not None:
        try:
            signed_graph = compile_release_to_graph(release.id, signed_policy)
        except (TypeError, ValueError):
            return False, "signed policy cannot be recompiled"
        if signed_graph.root_expression != compiled_rule_graph.root_expression:
            return False, "persisted compiled graph differs from the signed policy"

    return True, "verified"


def require_release_integrity_for_evaluation(
    release: Release,
    compiled_rule_graph: RuleGraph,
) -> None:
    """Fail closed for production evaluations while keeping legacy fixtures replayable locally."""
    if os.environ.get("IRE_ENV", "development").lower() != "production":
        return
    valid, reason = verify_release_bundle(release, compiled_rule_graph)
    if not valid:
        raise ReleaseIntegrityError(reason)
