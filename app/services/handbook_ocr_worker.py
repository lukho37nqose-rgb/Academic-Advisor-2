"""Worker for untrusted OCR candidates from scanned handbook pages.

This worker never overwrites handbook page text. It creates review proposals;
only a staff review action may update a page checkpoint.
"""

import argparse
import asyncio
import hashlib
import tempfile

from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.repositories import HandbookRepository, HandbookUploadConflictError
from app.services.ocr_provider import (
    OCRProviderResponseError,
    OCRProviderUnavailableError,
    extract_page_candidates,
    provider_name,
)
from app.services.tenant_context import production_background_scope_required, tenant_scope


async def _claim_upload(handbook_id: str):
    async with AsyncSessionLocal() as session:
        return await HandbookRepository(session).claim_ocr_upload(handbook_id)


async def _mark_failed(handbook_id: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        await HandbookRepository(session).mark_ocr_failed(handbook_id, message)


async def _process_handbook_ocr(handbook_id: str) -> bool:
    upload = await _claim_upload(handbook_id)
    if upload is None:
        return False

    try:
        if not upload.content_hash:
            raise HandbookUploadConflictError("The handbook source has not been hash-verified.")
        async with AsyncSessionLocal() as session:
            blank_pages = await HandbookRepository(session).list_blank_page_numbers(handbook_id)
        if not blank_pages:
            raise HandbookUploadConflictError("This handbook source has no scanned pages awaiting OCR review.")

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as source_file:
            source_hash = hashlib.sha256()
            async for chunk in BlobStorage.get_stream(upload.storage_key):
                source_hash.update(chunk)
                source_file.write(chunk)
            if source_hash.hexdigest() != upload.content_hash:
                raise HandbookUploadConflictError("Source hash verification failed before OCR.")

            candidates = await extract_page_candidates(
                source_file,
                file_name=upload.file_name,
                expected_pages=blank_pages,
            )

        async with AsyncSessionLocal() as session:
            repository = HandbookRepository(session)
            for candidate in candidates:
                await repository.save_ocr_candidate(
                    handbook_id=handbook_id,
                    tenant_id=upload.tenant_id,
                    page_number=candidate.page_number,
                    provider_name=provider_name(),
                    provider_reference=candidate.provider_reference,
                    proposed_text=candidate.text,
                    commit=False,
                )
            await session.commit()

        async with AsyncSessionLocal() as session:
            await HandbookRepository(session).mark_ocr_review_required(handbook_id)
        return True
    except OCRProviderUnavailableError:
        await _mark_failed(
            handbook_id,
            "OCR is unavailable. Provide an accessible text source or use an approved assisted transcription pathway.",
        )
    except OCRProviderResponseError:
        await _mark_failed(
            handbook_id,
            "OCR did not return reviewable text for every scanned page. The source remains pending manual review.",
        )
    except HandbookUploadConflictError as exc:
        await _mark_failed(handbook_id, str(exc))
    except Exception:
        await _mark_failed(
            handbook_id,
            "OCR processing could not be completed. The source remains pending manual review.",
        )
    return False


async def process_handbook_ocr(handbook_id: str, tenant_id: str | None = None) -> bool:
    """Processes OCR candidates only within the tenant supplied by the job payload."""
    if tenant_id is None:
        if production_background_scope_required():
            raise RuntimeError("Production OCR work requires an explicit tenant_id for row-level security.")
        return await _process_handbook_ocr(handbook_id)
    with tenant_scope(tenant_id):
        return await _process_handbook_ocr(handbook_id)


async def _main(handbook_id: str, tenant_id: str | None) -> None:
    processed = await process_handbook_ocr(handbook_id, tenant_id)
    print(f"Handbook OCR {handbook_id}: {'processed' if processed else 'not processed'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create review-only OCR proposals for a handbook source.")
    parser.add_argument("handbook_id")
    parser.add_argument("--tenant-id")
    args = parser.parse_args()
    asyncio.run(_main(args.handbook_id, args.tenant_id))
