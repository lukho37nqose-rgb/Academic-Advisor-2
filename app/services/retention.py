"""Scheduled retention task for human-assistance and decision-review records."""

import asyncio
from contextlib import nullcontext

from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.repositories import DecisionReviewRepository, PublicAccessRepository
from app.services.tenant_context import (
    configured_retention_tenant_ids,
    production_background_scope_required,
    tenant_scope,
)


async def purge_expired_support_requests(tenant_id: str | None = None) -> int:
    if tenant_id is None and production_background_scope_required():
        raise RuntimeError("Production retention work requires an explicit tenant_id for row-level security.")
    with tenant_scope(tenant_id) if tenant_id else nullcontext():
        async with AsyncSessionLocal() as session:
            return await PublicAccessRepository(session).purge_expired_support_requests()


async def purge_expired_decision_reviews(tenant_id: str | None = None) -> int:
    if tenant_id is None and production_background_scope_required():
        raise RuntimeError("Production retention work requires an explicit tenant_id for row-level security.")
    with tenant_scope(tenant_id) if tenant_id else nullcontext():
        async with AsyncSessionLocal() as session:
            return await DecisionReviewRepository(session).purge_expired_cases()


async def _main() -> None:
    tenant_ids = configured_retention_tenant_ids()
    if not tenant_ids:
        support_deleted = await purge_expired_support_requests()
        review_deleted = await purge_expired_decision_reviews()
    else:
        support_deleted = sum([await purge_expired_support_requests(tenant_id) for tenant_id in tenant_ids])
        review_deleted = sum([await purge_expired_decision_reviews(tenant_id) for tenant_id in tenant_ids])
    print(f"Purged {support_deleted} expired support requests and {review_deleted} expired decision review cases.")


if __name__ == "__main__":
    asyncio.run(_main())
