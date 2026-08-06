from __future__ import annotations

from pathlib import Path

from app.sdk.pilot_preflight import PilotManifest, assess_manifest


def _manifest(**overrides):
    payload = {
        "mode": "LOCAL_REHEARSAL",
        "institution_name": "Example University",
        "faculty_or_unit": "Faculty of Humanities",
        "decision_name": "Named prerequisite rehearsal",
        "decision_statement": "Test whether one named prerequisite is satisfied under one confirmed handbook edition; the result remains non-operative.",
        "out_of_scope": ["No operative decision"],
        "sources": [
            {
                "reference": "Humanities handbook 2026, programme rules",
                "kind": "POLICY_HANDBOOK",
                "authoritative": True,
                "effective_period_confirmed": True,
                "version_confirmed": True,
            },
            {
                "reference": "consented subject transcript local copy",
                "kind": "TRANSCRIPT",
                "authoritative": False,
                "effective_period_confirmed": True,
                "version_confirmed": True,
            },
        ],
        "data_boundaries": [
            {
                "reference": "policy handbook",
                "basis": "PUBLIC_POLICY",
                "contains_direct_identifiers": False,
                "storage_boundary": "LOCAL_ONLY",
            },
            {
                "reference": "subject consent record",
                "basis": "CONSENTED_SUBJECT_OWNED",
                "contains_direct_identifiers": True,
                "storage_boundary": "LOCAL_ONLY",
                "approval_reference": "consent-2026-001",
            },
        ],
        "gates": [
            {"id": gate_id, "accepted": True, "note": "Confirmed for the local rehearsal."}
            for gate_id in (
                "bounded_decision", "non_operative_use", "policy_versioning", "source_provenance",
                "transcript_minimisation", "human_review_route", "expected_cases", "no_repository_storage",
            )
        ],
        "external_ocr_enabled": False,
        "external_ai_enabled": False,
    }
    payload.update(overrides)
    return PilotManifest.model_validate(payload)


def _institutional_shadow_manifest(**overrides):
    payload = _manifest(mode="INSTITUTIONAL_SHADOW").model_dump(mode="json")
    payload.update(
        {
            "sources": [
                {
                    "reference": "UCT Humanities handbook 2026, official web edition",
                    "kind": "POLICY_HANDBOOK",
                    "authoritative": True,
                    "effective_period_confirmed": True,
                    "version_confirmed": True,
                },
                {
                    "reference": "privacy-approved de-identified historical decision set",
                    "kind": "RECORDED_OUTCOME",
                    "authoritative": True,
                    "effective_period_confirmed": True,
                    "version_confirmed": True,
                },
            ],
            "data_boundaries": [
                {
                    "reference": "public handbook",
                    "basis": "PUBLIC_POLICY",
                    "contains_direct_identifiers": False,
                    "storage_boundary": "TENANT_CONTROLLED",
                },
                {
                    "reference": "privacy approval for de-identified cases",
                    "basis": "APPROVED_DEIDENTIFIED",
                    "contains_direct_identifiers": False,
                    "storage_boundary": "TENANT_CONTROLLED",
                    "approval_reference": "privacy-shadow-approval-001",
                },
            ],
            "owners": [
                {"role": role, "name_or_office": f"{role} office", "confirmed": True, "note": "Confirmed for shadow pilot."}
                for role in (
                    "policy_owner",
                    "release_approver",
                    "identity_owner",
                    "privacy_security_lead",
                    "system_owner",
                    "student_support_lead",
                    "appeals_owner",
                    "deployment_owner",
                )
            ],
            "identity_plan": {
                "status": "PROVIDED",
                "issuer": "https://idp.example.edu",
                "audience": "ire-shadow-pilot",
                "jwks_url": "https://idp.example.edu/.well-known/jwks.json",
                "tenant_claim": "tenant",
                "role_claim": "role",
                "domain_claim": "domains",
                "subject_id_claim": "subject_id",
                "test_identities_count": 4,
            },
            "deployment_plan": {
                "hosting_boundary": "INSTITUTION_APPROVED_NON_PRODUCTION",
                "aws_account_status": "PROVIDED",
                "terraform_state_status": "PROVIDED",
                "database_boundary": "MANAGED_POSTGRES",
                "object_storage_boundary": "PRIVATE_OBJECT_STORE",
                "dns_tls_status": "PROVIDED",
                "secrets_management_status": "PROVIDED",
                "note": "Institution-approved non-production shadow environment.",
            },
            "operational_controls": [
                {"id": control_id, "status": "PROVIDED", "owner_reference": "pilot-owner", "approval_reference": "control-approval-001", "note": "Approved for shadow pilot."}
                for control_id in (
                    "retention_schedule",
                    "object_immutability",
                    "backup_restore_test",
                    "incident_contact",
                    "accessibility_route",
                    "security_review",
                    "malware_scanning",
                    "monitoring_owner",
                )
            ],
            "integrations": [
                {
                    "system_name": "PeopleSoft",
                    "integration_type": "MANUAL_MINIMISED_EXPORT",
                    "status": "PROVIDED",
                    "owner_reference": "system-owner",
                    "schema_or_export_reference": "shadow-export-v1",
                    "note": "Manual minimised export only; no write-back.",
                }
            ],
        }
    )
    payload.update(overrides)
    return PilotManifest.model_validate(payload)


def test_local_rehearsal_preflight_is_ready_only_with_all_controls():
    report = assess_manifest(_manifest())

    assert report.ready is True
    assert report.mode == "LOCAL_REHEARSAL"
    assert "not a UCT pilot" in report.warnings[0]


def test_preflight_blocks_unknown_policy_version_and_unaccepted_gate():
    payload = _manifest().model_dump()
    payload["sources"][0]["version_confirmed"] = False
    payload["gates"][0]["accepted"] = False

    report = assess_manifest(PilotManifest.model_validate(payload))

    assert report.ready is False
    assert any("bounded_decision" in blocker for blocker in report.blockers)
    assert any("version and effective period" in blocker for blocker in report.blockers)


def test_local_rehearsal_cannot_enable_external_processing():
    payload = _manifest().model_dump()
    payload["external_ocr_enabled"] = True

    try:
        PilotManifest.model_validate(payload)
    except ValueError as exc:
        assert "cannot enable external OCR" in str(exc)
    else:
        raise AssertionError("Local rehearsal must reject external OCR processing.")


def test_institutional_shadow_requires_owners_identity_and_operational_controls():
    payload = _manifest(mode="INSTITUTIONAL_SHADOW").model_dump(mode="json")
    payload["sources"][0]["authoritative"] = True
    payload["sources"][0]["effective_period_confirmed"] = True
    payload["sources"][0]["version_confirmed"] = True

    report = assess_manifest(PilotManifest.model_validate(payload))

    assert report.ready is False
    assert any("Missing confirmed institutional owners" in blocker for blocker in report.blockers)
    assert any("OIDC/JWKS" in blocker for blocker in report.blockers)
    assert any("managed PostgreSQL" in blocker for blocker in report.blockers)


def test_institutional_shadow_preflight_passes_with_all_required_controls():
    report = assess_manifest(_institutional_shadow_manifest())

    assert report.ready is True
    assert report.confirmed_owner_count == 8
    assert report.operational_control_count == 8
    assert report.integration_count == 1


def test_shadow_manifest_rejects_write_back_integrations():
    payload = _institutional_shadow_manifest().model_dump(mode="json")
    payload["integrations"][0]["integration_type"] = "WRITE_BACK"

    try:
        PilotManifest.model_validate(payload)
    except ValueError as exc:
        assert "write-back" in str(exc)
    else:
        raise AssertionError("Shadow pilots must reject write-back integrations.")


def test_uct_manifest_templates_parse_and_remain_blocked_until_completed():
    template_dir = Path(__file__).resolve().parents[1] / "pilot" / "uct_humanities"

    for template_name in ("pilot_manifest.template.json", "institutional_shadow_manifest.template.json"):
        manifest = PilotManifest.model_validate_json((template_dir / template_name).read_text(encoding="utf-8"))
        report = assess_manifest(manifest)

        assert report.ready is False
        assert report.blockers
