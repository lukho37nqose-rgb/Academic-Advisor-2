"""Durable, tenant-scoped worker for handbook source processing.

The queue is stored in PostgreSQL with the source record. Redis remains useful
for request protection and idempotency, but it is not the authority for work
that must survive a process restart. A worker always claims work under one
explicit tenant context, so PostgreSQL RLS remains active for every lookup.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
from dataclasses import dataclass
from typing import Literal, cast

from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.db import DBBackgroundJob
from app.infrastructure.repositories import BackgroundJobRepository, HandbookRepository
from app.services.background_job_signals import (
    BackgroundJobSignalError,
    delete_background_job_signal,
    receive_background_job_signals,
    signal_queue_configured,
)
from app.services.handbook_ocr_worker import process_handbook_ocr
from app.services.handbook_worker import process_handbook_upload
from app.services.tenant_context import production_background_scope_required, tenant_scope


class BackgroundJobExecutionError(RuntimeError):
    """Raised when a worker handler cannot establish a safe terminal result."""


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackgroundJobResult:
    job_id: str
    status: Literal["SUCCEEDED", "QUEUED", "DEAD_LETTER"]


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number.") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def background_job_lease_seconds() -> int:
    return _bounded_int("IRE_BACKGROUND_JOB_LEASE_SECONDS", 900, 30, 86_400)


def background_job_poll_seconds() -> int:
    return _bounded_int("IRE_BACKGROUND_JOB_POLL_SECONDS", 5, 1, 300)


def configured_worker_tenant_ids() -> tuple[str, ...]:
    values = tuple(
        value.strip()
        for value in os.environ.get("IRE_WORKER_TENANT_IDS", "").split(",")
        if value.strip()
    )
    if len(set(values)) != len(values):
        raise RuntimeError("IRE_WORKER_TENANT_IDS must not contain duplicate tenant identifiers.")
    if production_background_scope_required() and not values:
        raise RuntimeError(
            "Production durable workers require IRE_WORKER_TENANT_IDS so each job runs under tenant RLS."
        )
    return values


def worker_identity() -> str:
    value = os.environ.get("IRE_WORKER_ID", f"handbook-worker:{socket.gethostname()}").strip()
    if not value or len(value) > 128:
        raise RuntimeError("IRE_WORKER_ID must be a non-empty identifier of at most 128 characters.")
    return value


async def _handbook_status(handbook_id: str, tenant_id: str) -> str:
    async with AsyncSessionLocal() as session:
        upload = await HandbookRepository(session).get_upload(handbook_id, tenant_id=tenant_id)
        if upload is None:
            raise BackgroundJobExecutionError("The source record is no longer available to the tenant worker.")
        return str(upload.status)


async def _execute(job: DBBackgroundJob) -> None:
    job_type = str(job.job_type)
    handbook_id = str(job.resource_id)
    tenant_id = str(job.tenant_id)
    if job_type == "HANDBOOK_TEXT_EXTRACTION":
        await process_handbook_upload(handbook_id, tenant_id)
        status = await _handbook_status(handbook_id, tenant_id)
        if status in {"READY_FOR_REVIEW", "NEEDS_MANUAL_REVIEW"}:
            return
        raise BackgroundJobExecutionError("Handbook extraction did not reach a reviewable source state.")
    if job_type == "HANDBOOK_OCR":
        await process_handbook_ocr(handbook_id, tenant_id)
        status = await _handbook_status(handbook_id, tenant_id)
        # OCR failures intentionally return to an assisted/manual path instead
        # of silently retrying an external provider with the same source.
        if status in {"OCR_REVIEW_REQUIRED", "NEEDS_MANUAL_REVIEW"}:
            return
        raise BackgroundJobExecutionError("Handbook OCR did not reach a human-review state.")
    raise BackgroundJobExecutionError("The durable worker received an unsupported job type.")


async def _execute_with_lease(job: DBBackgroundJob, *, worker_id: str, lease_seconds: int) -> None:
    task = asyncio.create_task(_execute(job))
    heartbeat_seconds = max(10, min(60, lease_seconds // 3))
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                async with AsyncSessionLocal() as session:
                    renewed = await BackgroundJobRepository(session).renew_lease(
                        job_id=str(job.id),
                        tenant_id=str(job.tenant_id),
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                if not renewed:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    raise BackgroundJobExecutionError("The worker lease was lost before handbook processing finished.")
        await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def process_next_background_job(
    tenant_id: str,
    *,
    worker_id: str | None = None,
    lease_seconds: int | None = None,
) -> BackgroundJobResult | None:
    """Claim and process one durable job without escaping the given tenant."""
    active_worker_id = worker_id or worker_identity()
    active_lease_seconds = lease_seconds or background_job_lease_seconds()
    with tenant_scope(tenant_id):
        async with AsyncSessionLocal() as session:
            job = await BackgroundJobRepository(session).claim_next(
                tenant_id=tenant_id,
                worker_id=active_worker_id,
                lease_seconds=active_lease_seconds,
            )
        if job is None:
            return None

        try:
            await _execute_with_lease(
                job,
                worker_id=active_worker_id,
                lease_seconds=active_lease_seconds,
            )
        except Exception:
            async with AsyncSessionLocal() as session:
                status = await BackgroundJobRepository(session).mark_failed(
                    job_id=str(job.id),
                    tenant_id=tenant_id,
                    worker_id=active_worker_id,
                    error_message="Worker handler did not reach a safe terminal state.",
                )
            return BackgroundJobResult(job_id=str(job.id), status=cast_job_status(status))

        async with AsyncSessionLocal() as session:
            await BackgroundJobRepository(session).mark_succeeded(
                job_id=str(job.id),
                tenant_id=tenant_id,
                worker_id=active_worker_id,
            )
        return BackgroundJobResult(job_id=str(job.id), status="SUCCEEDED")


def cast_job_status(value: str) -> Literal["QUEUED", "DEAD_LETTER"]:
    if value not in {"QUEUED", "DEAD_LETTER"}:
        raise RuntimeError("Durable job repository returned an unsupported failure state.")
    return cast(Literal["QUEUED", "DEAD_LETTER"], value)


async def run_worker(tenant_ids: tuple[str, ...], *, once: bool = False) -> None:
    if not tenant_ids:
        raise RuntimeError("At least one explicit tenant identifier is required for durable worker execution.")
    while True:
        processed = False
        if signal_queue_configured() and not once:
            try:
                signals = await receive_background_job_signals(
                    allowed_tenant_ids=set(tenant_ids),
                    wait_seconds=background_job_poll_seconds(),
                )
            except BackgroundJobSignalError as exc:
                logger.warning("Background job signal receive failed: %s", exc)
                signals = []
            for signal in signals:
                result = await process_next_background_job(signal.tenant_id)
                processed = processed or result is not None
                try:
                    await delete_background_job_signal(signal.receipt_handle)
                except BackgroundJobSignalError as exc:
                    logger.warning("Background job signal delete failed for %s: %s", signal.job_id, exc)
        for tenant_id in tenant_ids:
            result = await process_next_background_job(tenant_id)
            processed = processed or result is not None
        if once:
            return
        if not processed:
            await asyncio.sleep(background_job_poll_seconds())


def _main() -> None:
    parser = argparse.ArgumentParser(description="Process durable handbook jobs under explicit tenant RLS scopes.")
    parser.add_argument("--tenant-id", action="append", dest="tenant_ids")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    tenant_ids = tuple(args.tenant_ids) if args.tenant_ids else configured_worker_tenant_ids()
    asyncio.run(run_worker(tenant_ids, once=args.once))


if __name__ == "__main__":
    _main()
