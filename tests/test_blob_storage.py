from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

import pytest

from app.infrastructure.blob_storage import BlobStorage


async def _read_object(key: str) -> bytes:
    return b"".join([chunk async for chunk in BlobStorage.get_stream(key)])


def test_new_objects_are_tenant_scoped_and_content_addressed() -> None:
    async def run() -> None:
        content = "An institution controls its own decision rules."
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

        evidence_key = await BlobStorage.upload_text(content, tenant_id="tenant_one")
        source_key = await BlobStorage.upload_binary(
            BytesIO(b"%PDF-1.7"),
            tenant_id="tenant_one",
            content_hash=hashlib.sha256(b"%PDF-1.7").hexdigest(),
            suffix=".pdf",
        )

        assert evidence_key == f"tenants/tenant_one/evidence/{digest}.txt"
        assert source_key.startswith("tenants/tenant_one/sources/")
        assert await _read_object(evidence_key) == content.encode("utf-8")

    BlobStorage._store.clear()
    try:
        asyncio.run(run())
    finally:
        BlobStorage._store.clear()


def test_unsafe_storage_key_components_are_rejected() -> None:
    digest = hashlib.sha256(b"source").hexdigest()

    with pytest.raises(ValueError, match="Tenant identifier"):
        BlobStorage.tenant_prefix("tenant/other")

    async def run() -> None:
        with pytest.raises(ValueError, match="content hash"):
            await BlobStorage.upload_binary(
                BytesIO(b"source"),
                tenant_id="tenant_one",
                content_hash="not-a-sha256-digest",
                suffix=".pdf",
            )
        with pytest.raises(ValueError, match="suffix"):
            await BlobStorage.upload_binary(
                BytesIO(b"source"),
                tenant_id="tenant_one",
                content_hash=digest,
                suffix=".pdf/../other",
            )

    asyncio.run(run())
