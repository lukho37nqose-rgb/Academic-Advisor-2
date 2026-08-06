"""Provider control-plane metadata stays separate from institutional data."""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.db import Base
from app.infrastructure.repositories import ProviderOperationsRepository


def test_provider_can_provision_and_manage_only_tenant_lifecycle(tmp_path):
    database_path = tmp_path / "provider_controls.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def exercise():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            repository = ProviderOperationsRepository(session)
            provisioned = await repository.provision_tenant(
                tenant_id="pilot_uct",
                tenant_name="Pilot University",
                actor_id="provider_operator_1",
            )
            updated = await repository.update_lifecycle(
                tenant_id="pilot_uct",
                lifecycle_state="ACTIVE",
                actor_id="provider_operator_1",
            )
            support = await repository.request_support_access(
                tenant_id="pilot_uct",
                actor_id="provider_operator_1",
                reason="Investigating a tenant-reported integration health alert.",
            )
            return provisioned, updated, support, await repository.list_tenants()

    provisioned, updated, support, tenants = asyncio.run(exercise())
    asyncio.run(engine.dispose())

    assert provisioned["lifecycle_state"] == "PILOT"
    assert provisioned["integration_status"] == "NOT_CONFIGURED"
    assert updated and updated["lifecycle_state"] == "ACTIVE"
    assert support and support["status"] == "REQUESTED"
    assert tenants == [updated]
