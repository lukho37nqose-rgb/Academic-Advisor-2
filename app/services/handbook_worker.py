"""Worker entry point for page-level handbook text extraction.

This worker never creates policy drafts or releases. It turns a verified PDF
source into reviewable page text only.
"""

import argparse
import asyncio
import hashlib
import tempfile

from pypdf import PdfReader

from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.repositories import HandbookRepository
from app.services.tenant_context import production_background_scope_required, tenant_scope


async def _claim_upload(handbook_id: str):
    async with AsyncSessionLocal() as session:
        return await HandbookRepository(session).claim_queued_upload(handbook_id)


async def _mark_failed(handbook_id: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        await HandbookRepository(session).mark_failed(handbook_id, message)


async def _process_handbook_upload(handbook_id: str) -> bool:
    upload = await _claim_upload(handbook_id)
    if upload is None:
        return False

    try:
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as source_file:
            source_hash = hashlib.sha256()
            async for chunk in BlobStorage.get_stream(upload.storage_key):
                source_hash.update(chunk)
                source_file.write(chunk)
            content_hash = source_hash.hexdigest()
            if upload.content_hash is not None and content_hash != upload.content_hash:
                raise ValueError("Source hash verification failed after storage retrieval.")

            if upload.content_hash is None:
                canonical_key = await BlobStorage.upload_binary(
                    source_file,
                    content_hash=content_hash,
                    suffix=".pdf",
                )
                async with AsyncSessionLocal() as session:
                    await HandbookRepository(session).record_verified_source(
                        handbook_id,
                        content_hash=content_hash,
                        storage_key=canonical_key,
                    )
            source_file.seek(0)
            reader = PdfReader(source_file)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs must be decrypted before handbook extraction.")

            async with AsyncSessionLocal() as session:
                await HandbookRepository(session).set_total_pages(handbook_id, len(reader.pages))

            start_page = upload.processed_pages + 1
            for page_number in range(start_page, len(reader.pages) + 1):
                page_text = reader.pages[page_number - 1].extract_text() or ""
                page_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
                async with AsyncSessionLocal() as session:
                    await HandbookRepository(session).save_page(
                        handbook_id=handbook_id,
                        page_number=page_number,
                        text_content=page_text,
                        content_hash=page_hash,
                    )

        async with AsyncSessionLocal() as session:
            repository = HandbookRepository(session)
            blank_pages = await repository.count_pages_without_text(handbook_id)
            if blank_pages:
                await repository.mark_needs_manual_review(
                    handbook_id,
                    f"{blank_pages} page(s) have no selectable text. Provide an accessible text-based source "
                    "or route this handbook for OCR and human review.",
                )
                return False
            await repository.mark_ready(handbook_id)
        return True
    except Exception as exc:
        await _mark_failed(handbook_id, str(exc))
        return False


async def process_handbook_upload(handbook_id: str, tenant_id: str | None = None) -> bool:
    """Processes a source only within the tenant supplied by the trusted job payload."""
    if tenant_id is None:
        if production_background_scope_required():
            raise RuntimeError("Production handbook work requires an explicit tenant_id for row-level security.")
        return await _process_handbook_upload(handbook_id)
    with tenant_scope(tenant_id):
        return await _process_handbook_upload(handbook_id)


async def _main(handbook_id: str, tenant_id: str | None) -> None:
    processed = await process_handbook_upload(handbook_id, tenant_id)
    print(f"Handbook {handbook_id}: {'processed' if processed else 'not processed'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract a queued handbook PDF page by page.")
    parser.add_argument("handbook_id")
    parser.add_argument("--tenant-id")
    args = parser.parse_args()
    asyncio.run(_main(args.handbook_id, args.tenant_id))
