"""Worker for untrusted OCR candidates from scanned handbook pages.

This worker never overwrites handbook page text. It creates review proposals;
only a staff review action may update a page checkpoint.
"""

import argparse
import asyncio
import hashlib
import tempfile

from pypdf import PdfReader, PdfWriter

from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.repositories import HandbookRepository, HandbookUploadConflictError
from app.services.ocr_provider import (
    OCRPageCandidate,
    OCRProviderResponseError,
    OCRProviderUnavailableError,
    extract_page_candidates,
    max_pages_per_job,
    max_pages_per_request,
    provider_name,
)
from app.services.tenant_context import production_background_scope_required, tenant_scope


async def _claim_upload(handbook_id: str):
    async with AsyncSessionLocal() as session:
        return await HandbookRepository(session).claim_ocr_upload(handbook_id)


async def _mark_failed(handbook_id: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        await HandbookRepository(session).mark_ocr_failed(handbook_id, message)


def _isolated_pdf_pages(source_file, page_numbers: list[int]) -> tuple[tempfile.SpooledTemporaryFile, dict[int, str]]:
    """Copy only requested original pages into a transient provider payload.

    The original handbook remains in private storage. Page identifiers are sent
    separately so an OCR provider can return citations using original numbers.
    """
    source_file.seek(0)
    reader = PdfReader(source_file)
    writer = PdfWriter()
    page_hashes: dict[int, str] = {}
    for page_number in page_numbers:
        page_writer = PdfWriter()
        page_writer.add_page(reader.pages[page_number - 1])
        page_bytes = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b")
        page_writer.write(page_bytes)
        page_bytes.seek(0)
        page_hashes[page_number] = hashlib.sha256(page_bytes.read()).hexdigest()
        page_bytes.close()
        writer.add_page(reader.pages[page_number - 1])
    isolated = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    writer.write(isolated)
    isolated.seek(0)
    return isolated, page_hashes


def _candidate_priority(candidate) -> str:
    """Prioritise review; it never decides whether review is required."""
    signals = candidate.quality_signals
    text = candidate.text.lower()
    policy_terms = ("prerequisite", "credit", "progression", "exclusion", "must", "shall")
    if signals.low_quality_scan or signals.handwritten or signals.contains_table:
        return "HIGH"
    if any(term in text for term in policy_terms) or any(character.isdigit() for character in text):
        return "HIGH"
    return "NORMAL"


def _serialise_candidate_signals(candidate) -> dict[str, object]:
    return candidate.quality_signals.model_dump(mode="json")


def _serialise_candidate_blocks(candidate) -> list[dict[str, object]]:
    return [block.model_dump(mode="json") for block in candidate.blocks]


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
        if len(blank_pages) > max_pages_per_job():
            raise HandbookUploadConflictError(
                "This OCR request exceeds the institution's OCR_MAX_PAGES_PER_JOB limit. Split the source or use assisted transcription."
            )

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as source_file:
            source_hash = hashlib.sha256()
            async for chunk in BlobStorage.get_stream(upload.storage_key):
                source_hash.update(chunk)
                source_file.write(chunk)
            if source_hash.hexdigest() != upload.content_hash:
                raise HandbookUploadConflictError("Source hash verification failed before OCR.")

            candidates_with_provenance: list[tuple[OCRPageCandidate, str | None, str, str]] = []
            request_limit = max_pages_per_request()
            for start in range(0, len(blank_pages), request_limit):
                requested_pages = blank_pages[start:start + request_limit]
                isolated_pages, page_hashes = _isolated_pdf_pages(source_file, requested_pages)
                try:
                    result = await extract_page_candidates(
                        isolated_pages,
                        file_name=f"{upload.id}-pages-{requested_pages[0]}-{requested_pages[-1]}.pdf",
                        expected_pages=requested_pages,
                    )
                finally:
                    isolated_pages.close()
                # Retain compatibility with a narrow test double while the
                # production adapter returns model and response provenance.
                if isinstance(result, tuple):
                    candidates, model_version, response_hash = result
                else:
                    candidates, model_version, response_hash = result, None, None
                for candidate in candidates:
                    candidates_with_provenance.append((
                        candidate,
                        model_version,
                        response_hash or hashlib.sha256(candidate.text.encode("utf-8")).hexdigest(),
                        page_hashes[candidate.page_number],
                    ))

        async with AsyncSessionLocal() as session:
            repository = HandbookRepository(session)
            for candidate, model_version, response_hash, source_page_hash in candidates_with_provenance:
                await repository.save_ocr_candidate(
                    handbook_id=handbook_id,
                    tenant_id=upload.tenant_id,
                    page_number=candidate.page_number,
                    provider_name=provider_name(),
                    provider_reference=candidate.provider_reference,
                    proposed_text=candidate.text,
                    provider_model_version=model_version,
                    provider_response_hash=response_hash,
                    source_page_hash=source_page_hash,
                    proposed_blocks=_serialise_candidate_blocks(candidate),
                    quality_signals=_serialise_candidate_signals(candidate),
                    review_priority=_candidate_priority(candidate),
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
