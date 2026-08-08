from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.engine import generate_reasoning_graph
from app.core.models import EvaluationContext, ExpressionNode, ReasoningGraph, RuleGraph
from app.core.replay import verify_decision_snapshot
from app.infrastructure.db import (
    Base,
    DBDomain,
    DBEvidence,
    DBEvidenceFactProposal,
    DBRelease,
    DBRuleGraph,
    DBTenant,
)
from app.infrastructure.repositories import InstitutionalPositionRepository, ReleaseRepository
from app.services.institutional_position import (
    InstitutionalPositionFact,
    PositionSelectionConflictError,
    compare_positions,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _tenant_domain(session, tenant_id: str = "tenant_position", domain_id: str = "dom_position") -> None:
    session.add(DBTenant(id=tenant_id, name="Position Institution"))
    session.add(
        DBDomain(
            id=domain_id,
            tenant_id=tenant_id,
            name="Position domain",
            schema_definition={
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "object",
                        "properties": {
                            "registration_load": {"type": "number", "title": "Registered load"},
                            "registration_active": {"type": "boolean", "title": "Registration active"},
                        },
                    },
                },
            },
        )
    )


def _evidence(
    *,
    evidence_id: str,
    tenant_id: str = "tenant_position",
    domain_id: str = "dom_position",
    subject_id: str = "subject_position",
    value_time: str,
    recorded_time: str,
    record_state: str = "confirmed",
    source_system: str = "Synthetic registration record",
    source_record_version: str = "v1",
) -> DBEvidence:
    return DBEvidence(
        id=evidence_id,
        tenant_id=tenant_id,
        domain_id=domain_id,
        subject_id=subject_id,
        source_type="system_record_export",
        source_authority="official_system",
        record_state=record_state,
        source_system=source_system,
        source_record_version=source_record_version,
        source_as_of=_dt(value_time),
        cryptographic_hash="sha256:" + evidence_id,
        timestamp=_dt(recorded_time),
    )


def _proposal(
    *,
    proposal_id: str,
    evidence_id: str,
    value: Any,
    target_path: str = "facts.registration_load",
    tenant_id: str = "tenant_position",
    domain_id: str = "dom_position",
    subject_id: str = "subject_position",
    status: str = "ACCEPTED",
    reviewed_at: str | None = "2027-03-02T09:00:00Z",
) -> DBEvidenceFactProposal:
    return DBEvidenceFactProposal(
        id=proposal_id,
        tenant_id=tenant_id,
        domain_id=domain_id,
        evidence_id=evidence_id,
        subject_id=subject_id,
        target_path=target_path,
        asserted_value=value,
        source_quote=f"{target_path} = {value}",
        source_locator="Synthetic registration export",
        extraction_confidence=1.0,
        source_trust_level=1.0,
        proposal_origin="MANUAL",
        evidence_sha256="sha256:" + evidence_id,
        input_sha256="input:" + proposal_id,
        proposed_by="records_author",
        status=status,
        reviewed_by="records_reviewer" if status in {"ACCEPTED", "REJECTED"} else None,
        review_note="Independently reviewed." if status in {"ACCEPTED", "REJECTED"} else None,
        reviewed_at=_dt(reviewed_at) if reviewed_at else None,
        created_at=_dt("2027-03-01T12:00:00Z"),
    )


def test_position_selection_respects_effective_time_governance_and_scope(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'position.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _run() -> None:
        await _schema(engine)
        async with session_factory.begin() as session:
            _tenant_domain(session)
            session.add_all(
                [
                    _evidence(evidence_id="ev_load_96", value_time="2027-03-01T00:00:00Z", recorded_time="2027-03-02T08:00:00Z"),
                    _proposal(proposal_id="efp_load_96", evidence_id="ev_load_96", value=96),
                    _evidence(
                        evidence_id="ev_load_72",
                        value_time="2027-04-22T00:00:00Z",
                        recorded_time="2027-04-25T08:00:00Z",
                        source_record_version="v2",
                    ),
                    _proposal(
                        proposal_id="efp_load_72",
                        evidence_id="ev_load_72",
                        value=72,
                        reviewed_at="2027-04-25T09:00:00Z",
                    ),
                    _evidence(evidence_id="ev_pending", value_time="2027-03-05T00:00:00Z", recorded_time="2027-03-05T08:00:00Z"),
                    _proposal(proposal_id="efp_pending", evidence_id="ev_pending", value=120, status="PENDING", reviewed_at=None),
                    _evidence(evidence_id="ev_rejected", value_time="2027-03-06T00:00:00Z", recorded_time="2027-03-06T08:00:00Z"),
                    _proposal(
                        proposal_id="efp_rejected",
                        evidence_id="ev_rejected",
                        value=24,
                        status="REJECTED",
                        reviewed_at="2027-03-07T09:00:00Z",
                    ),
                    _evidence(
                        evidence_id="ev_provisional",
                        value_time="2027-03-08T00:00:00Z",
                        recorded_time="2027-03-08T08:00:00Z",
                        record_state="provisional",
                    ),
                    _proposal(
                        proposal_id="efp_provisional",
                        evidence_id="ev_provisional",
                        value=48,
                        reviewed_at="2027-03-09T09:00:00Z",
                    ),
                    _evidence(
                        evidence_id="ev_other_subject",
                        subject_id="subject_other",
                        value_time="2027-03-01T00:00:00Z",
                        recorded_time="2027-03-02T08:00:00Z",
                    ),
                    _proposal(
                        proposal_id="efp_other_subject",
                        evidence_id="ev_other_subject",
                        subject_id="subject_other",
                        value=999,
                    ),
                ]
            )

        async with session_factory() as session:
            repo = InstitutionalPositionRepository(session)
            before_change = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_position",
                effective_at=_dt("2027-04-20T12:00:00Z"),
                known_at=_dt("2027-04-20T12:00:00Z"),
            )
            not_yet_known = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_position",
                effective_at=_dt("2027-04-23T12:00:00Z"),
                known_at=_dt("2027-04-23T12:00:00Z"),
            )
            after_change = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_position",
                effective_at=_dt("2027-04-23T12:00:00Z"),
                known_at=_dt("2027-04-26T12:00:00Z"),
            )
            other_subject = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_other",
                effective_at=_dt("2027-04-23T12:00:00Z"),
                known_at=_dt("2027-04-26T12:00:00Z"),
            )

        assert [fact.resolved_value for fact in before_change.facts] == [96]
        assert [fact.resolved_value for fact in not_yet_known.facts] == [96]
        assert [fact.resolved_value for fact in after_change.facts] == [72]
        assert after_change.facts[0].source_record_version == "v2"
        assert after_change.facts[0].source_as_of == _dt("2027-04-22T00:00:00Z")
        assert after_change.omitted_counts == {"pending": 1, "rejected": 1, "provisional": 1}
        assert [fact.resolved_value for fact in other_subject.facts] == [999]
        changes = compare_positions(before_change, after_change)
        assert [(change.prior_value, change.new_value, change.effective_at) for change in changes] == [
            (96, 72, _dt("2027-04-22T00:00:00Z"))
        ]

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_position_selection_rejects_conflicting_accepted_facts(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'conflict.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _run() -> None:
        await _schema(engine)
        async with session_factory.begin() as session:
            _tenant_domain(session)
            session.add_all(
                [
                    _evidence(evidence_id="ev_a", value_time="2027-03-01T00:00:00Z", recorded_time="2027-03-02T08:00:00Z"),
                    _proposal(proposal_id="efp_a", evidence_id="ev_a", value=96),
                    _evidence(evidence_id="ev_b", value_time="2027-03-01T00:00:00Z", recorded_time="2027-03-02T08:30:00Z"),
                    _proposal(proposal_id="efp_b", evidence_id="ev_b", value=72),
                ]
            )
        async with session_factory() as session:
            with pytest.raises(PositionSelectionConflictError):
                await InstitutionalPositionRepository(session).position_for(
                    tenant_id="tenant_position",
                    domain_id="dom_position",
                    subject_id="subject_position",
                    effective_at=_dt("2027-03-02T12:00:00Z"),
                    known_at=_dt("2027-03-03T12:00:00Z"),
                )

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_historical_decision_replays_from_persisted_snapshot_not_later_position(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'history.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    rule_graph = RuleGraph(
        id="rg_registration_load",
        release_id="rel_2027",
        compiled_at="2027-01-01T00:00:00+00:00",
        root_expression=ExpressionNode(
            id="load_rule",
            label="Registered load meets the threshold",
            target="facts.registration_load",
            condition=">=",
            value=80,
            source_citation="Synthetic progression rule",
            policy_source={
                "source_id": "source_2027",
                "source_version": "2027",
                "source_title": "Synthetic Rule Source 2027",
                "page_start": 13,
                "section": "2.1",
            },
        ),
    )

    async def _run() -> None:
        await _schema(engine)
        async with session_factory.begin() as session:
            _tenant_domain(session)
            session.add_all(
                [
                    _evidence(evidence_id="ev_load_96", value_time="2027-03-01T00:00:00Z", recorded_time="2027-03-02T08:00:00Z"),
                    _proposal(proposal_id="efp_load_96", evidence_id="ev_load_96", value=96),
                    _evidence(evidence_id="ev_load_72", value_time="2027-04-22T00:00:00Z", recorded_time="2027-04-25T08:00:00Z"),
                    _proposal(
                        proposal_id="efp_load_72",
                        evidence_id="ev_load_72",
                        value=72,
                        reviewed_at="2027-04-25T09:00:00Z",
                    ),
                ]
            )
        async with session_factory() as session:
            repo = InstitutionalPositionRepository(session)
            march_position = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_position",
                effective_at=_dt("2027-03-10T12:00:00Z"),
                known_at=_dt("2027-03-10T12:00:00Z"),
            )
            april_position = await repo.position_for(
                tenant_id="tenant_position",
                domain_id="dom_position",
                subject_id="subject_position",
                effective_at=_dt("2027-04-26T12:00:00Z"),
                known_at=_dt("2027-04-26T12:00:00Z"),
            )

        context = EvaluationContext(
            tenant_id="tenant_position",
            domain_id="dom_position",
            subject_id="subject_position",
            release_version="2027.1",
            policy_as_of_date=date(2027, 3, 10),
            institutional_position_effective_at=_dt("2027-03-10T12:00:00Z"),
            institutional_position_known_at=_dt("2027-03-10T12:00:00Z"),
            position_context_kind="governed_institutional_position",
            timestamp="2027-03-10T12:00:00+00:00",
        )
        stored_graph = generate_reasoning_graph(context, rule_graph, march_position.as_reasoning_facts())
        later_graph = generate_reasoning_graph(
            context.model_copy(update={"timestamp": "2027-04-26T12:00:00+00:00"}),
            rule_graph,
            april_position.as_reasoning_facts(),
        )
        verified = await verify_decision_snapshot(
            stored_graph=stored_graph,
            rule_graph=rule_graph,
            stored_facts=march_position.as_reasoning_facts(),
            stored_decision="ELIGIBLE",
            stored_confidence=1.0,
        )
        rewritten = await verify_decision_snapshot(
            stored_graph=stored_graph,
            rule_graph=rule_graph,
            stored_facts=april_position.as_reasoning_facts(),
            stored_decision="ELIGIBLE",
            stored_confidence=1.0,
        )

        assert stored_graph.nodes["gn_fact_fact_efp_load_96"].data["resolved_value"] == 96
        assert stored_graph.nodes["gn_fact_fact_efp_load_96"].data["source_as_of"] == "2027-03-01T00:00:00+00:00"
        assert stored_graph.nodes["gn_eval_load_rule"].data["policy_source"]["source_id"] == "source_2027"
        assert "policy_source" not in stored_graph.nodes["gn_fact_fact_efp_load_96"].data
        assert later_graph.nodes["gn_fact_fact_efp_load_72"].data["resolved_value"] == 72
        assert later_graph.nodes["gn_conclusion_final"].data["overall_passed"] is False
        assert verified.status == "VERIFIED"
        assert rewritten.status == "FAILED"

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_policy_release_selection_is_effective_time_bound(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'release.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _run() -> None:
        await _schema(engine)
        async with session_factory.begin() as session:
            _tenant_domain(session)
            for release_id in ("rel_2026", "rel_2027"):
                session.add(
                    DBRuleGraph(
                        id=f"rg_{release_id}",
                        release_id=release_id,
                        compiled_bytecode={
                            "id": "root",
                            "label": "Rule",
                            "target": "facts.registration_load",
                            "condition": ">=",
                            "value": 80,
                        },
                    )
                )
            session.add_all(
                [
                    DBRelease(
                        id="rel_2026",
                        domain_id="dom_position",
                        version="2026.1",
                        rule_graph_id="rg_rel_2026",
                        digital_signature="sig",
                        effective_from=date(2026, 1, 1),
                        effective_until=date(2026, 12, 31),
                        applicability={"entry_year": ["2026"]},
                    ),
                    DBRelease(
                        id="rel_2027",
                        domain_id="dom_position",
                        version="2027.1",
                        rule_graph_id="rg_rel_2027",
                        digital_signature="sig",
                        effective_from=date(2027, 1, 1),
                        effective_until=None,
                        applicability={"entry_year": ["2027"]},
                    ),
                ]
            )
        async with session_factory() as session:
            repo = ReleaseRepository(session)
            release_2026 = await repo.get_applicable_release(
                domain_id="dom_position",
                as_of_date=date(2026, 6, 1),
                applicability_context={"entry_year": "2026"},
            )
            release_2027 = await repo.get_applicable_release(
                domain_id="dom_position",
                as_of_date=date(2027, 6, 1),
                applicability_context={"entry_year": "2027"},
            )
            mismatch = await repo.get_applicable_release(
                domain_id="dom_position",
                as_of_date=date(2027, 6, 1),
                applicability_context={"entry_year": "2026"},
            )
        assert release_2026 is not None and release_2026.version == "2026.1"
        assert release_2027 is not None and release_2027.version == "2027.1"
        assert mismatch is None

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_hypothetical_inputs_and_domain_examples_stay_out_of_the_core() -> None:
    with pytest.raises(ValidationError):
        InstitutionalPositionFact.model_validate(
            {
                "id": "fact_scenario",
                "target_path": "facts.registration_load",
                "resolved_value": 72,
                "final_confidence": 1.0,
                "governance_state": "HYPOTHETICAL",
                "source_authority": "subject_submitted",
                "record_state": "confirmed",
                "source_as_of": "2027-04-22T00:00:00Z",
                "evidence_id": "scenario_only",
                "proposal_id": "scenario_only",
            }
        )

    core_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("app/core").glob("*.py"))
    assert "registration" not in core_text.lower()
