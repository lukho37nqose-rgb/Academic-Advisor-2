import pytest
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.infrastructure.db import Base, DBFact, DBFactSupersessionEvent, DBReasoningGraph
from app.core.models import Fact, ReasoningGraph
from app.infrastructure.repositories import ReasoningRepository

def test_supersede_fact_preserves_audit_trail(tmp_path):
    """
    Proves that supersession is an append-only event and leaves both facts intact.
    """
    database_path = tmp_path / "successor.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _run_test():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as db_session:
            repo = ReasoningRepository(db_session)
            
            # 1. Setup: Create a dummy reasoning graph and two facts
            graph = ReasoningGraph(subject_id="sub_1", rule_graph_id="rule_1")
            await repo.save_evaluation_artifacts(
                graph=graph,
                overall_decision="ELIGIBLE",
                overall_confidence=1.0,
                tenant_id="tenant_1",
                domain_id="domain_1",
                release_id="rel_1",
                evidence_id="ev_1",
                claims=[],
                facts=[
                    Fact(id="fact_old", target_path="test.path", resolved_value=True, final_confidence=1.0),
                    Fact(id="fact_new", target_path="test.path", resolved_value=False, final_confidence=1.0)
                ]
            )
            
            # 2. Execute: Supersede the old fact with the new fact
            success = await repo.supersede_fact(
                old_fact_id="fact_old",
                new_fact_id="fact_new",
                tenant_id="tenant_1",
                domain_id="domain_1",
                actor_id="approver_1",
                reason="Correction based on new evidence"
            )
            assert success is True
            
            # 3. Verify: Both immutable fact rows remain unchanged.
            old_fact_db = await db_session.get(DBFact, "fact_old")
            assert old_fact_db is not None
            new_fact_db = await db_session.get(DBFact, "fact_new")
            assert new_fact_db is not None
            event = (await db_session.execute(
                __import__('sqlalchemy').select(DBFactSupersessionEvent)
            )).scalars().one()
            assert event.old_fact_id == "fact_old"
            assert event.new_fact_id == "fact_new"
            assert event.actor_id == "approver_1"

    asyncio.run(_run_test())
