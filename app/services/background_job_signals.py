"""Optional SQS wakeup signals for the durable PostgreSQL job ledger."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import aiobotocore.session
from botocore.exceptions import ClientError


class BackgroundJobSignalError(RuntimeError):
    """Raised when the optional SQS signal channel cannot be used safely."""


@dataclass(frozen=True)
class BackgroundJobSignal:
    tenant_id: str
    job_id: str
    receipt_handle: str


def signal_queue_url() -> str | None:
    value = os.environ.get("IRE_BACKGROUND_JOB_SIGNAL_QUEUE_URL", "").strip()
    return value or None


def signal_queue_configured() -> bool:
    return signal_queue_url() is not None


def _bounded_wait_seconds(wait_seconds: int) -> int:
    return max(0, min(wait_seconds, 20))


def _signal_body(job_summary: dict[str, Any]) -> str:
    payload = {
        "tenant_id": str(job_summary["tenant_id"]),
        "domain_id": str(job_summary["domain_id"]),
        "job_id": str(job_summary["job_id"]),
        "job_type": str(job_summary["job_type"]),
        "resource_id": str(job_summary["resource_id"]),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


async def publish_background_job_signal(job_summary: dict[str, Any]) -> bool:
    """Notify workers that the PostgreSQL job ledger has work available.

    The SQS message is not the authority for the job. It is a wakeup signal for
    workers that still claim and complete work through tenant-scoped database
    leases.
    """
    queue_url = signal_queue_url()
    if queue_url is None:
        return False
    session = aiobotocore.session.get_session()
    async with session.create_client("sqs") as client:
        try:
            await client.send_message(
                QueueUrl=queue_url,
                MessageBody=_signal_body(job_summary),
            )
        except ClientError as exc:
            raise BackgroundJobSignalError("Could not publish a background job signal.") from exc
    return True


async def receive_background_job_signals(
    *,
    allowed_tenant_ids: set[str],
    wait_seconds: int,
    max_messages: int = 10,
) -> list[BackgroundJobSignal]:
    queue_url = signal_queue_url()
    if queue_url is None:
        return []
    session = aiobotocore.session.get_session()
    async with session.create_client("sqs") as client:
        try:
            response = await client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max(1, min(max_messages, 10)),
                WaitTimeSeconds=_bounded_wait_seconds(wait_seconds),
            )
        except ClientError as exc:
            raise BackgroundJobSignalError("Could not receive background job signals.") from exc

    signals: list[BackgroundJobSignal] = []
    for message in response.get("Messages", []):
        try:
            body = json.loads(str(message.get("Body", "{}")))
        except json.JSONDecodeError:
            continue
        tenant_id = body.get("tenant_id")
        job_id = body.get("job_id")
        receipt_handle = message.get("ReceiptHandle")
        if not isinstance(tenant_id, str) or tenant_id not in allowed_tenant_ids:
            continue
        if not isinstance(job_id, str) or not isinstance(receipt_handle, str):
            continue
        signals.append(
            BackgroundJobSignal(
                tenant_id=tenant_id,
                job_id=job_id,
                receipt_handle=receipt_handle,
            )
        )
    return signals


async def delete_background_job_signal(receipt_handle: str) -> None:
    queue_url = signal_queue_url()
    if queue_url is None:
        return
    session = aiobotocore.session.get_session()
    async with session.create_client("sqs") as client:
        try:
            await client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        except ClientError as exc:
            raise BackgroundJobSignalError("Could not delete a background job signal.") from exc
