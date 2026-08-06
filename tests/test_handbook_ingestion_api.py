from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

import app.api as api_module
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.database import get_db_session
from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.db import (
    Base,
    DBBackgroundJob,
    DBHandbookOcrReviewEvent,
    DBHandbookPage,
    DBHandbookUpload,
    DBHandbookUploadSession,
)
from app.services.auth import Role, UserIdentity, get_current_user
from app.services import handbook_ocr_worker, handbook_worker
from app.services.ocr_provider import OCRPageCandidate


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _text_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Handbook rule text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def _blank_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def test_handbook_upload_is_queued_and_extracted_page_by_page(tmp_path, monkeypatch):
    database_path = tmp_path / "handbook_upload.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_handbook",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_handbook"],
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/governance/handbooks",
            data={"domain_id": "dom_handbook"},
            files={"file": ("handbook.pdf", _text_pdf(), "application/pdf")},
        )
        payload = response.json()
        listing = client.get("/api/v1/governance/handbooks")
        monkeypatch.setattr(handbook_worker, "AsyncSessionLocal", session_factory)
        extracted = asyncio.run(handbook_worker.process_handbook_upload(payload["handbook_id"]))

        async def _load_upload():
            async with session_factory() as session:
                upload = await session.get(DBHandbookUpload, payload["handbook_id"])
                page = await session.get(DBHandbookPage, f"handbook_page_{payload['handbook_id']}_1")
                job = (await session.execute(
                    select(DBBackgroundJob).where(DBBackgroundJob.resource_id == payload["handbook_id"])
                )).scalars().one()
                return upload, page, job

        upload, page, job = asyncio.run(_load_upload())
        page_review = client.get(f"/api/v1/governance/handbooks/{payload['handbook_id']}/pages")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 201
    assert payload["status"] == "QUEUED"
    assert job.status == "QUEUED"
    assert job.job_type == "HANDBOOK_TEXT_EXTRACTION"
    assert len(payload["content_hash"]) == 64
    assert "cannot publish a policy" in payload["next_step"]
    assert upload is not None
    assert upload.file_name == "handbook.pdf"
    assert extracted is True
    assert upload.status == "READY_FOR_REVIEW"
    assert upload.total_pages == 1
    assert upload.processed_pages == 1
    assert page is not None
    assert page.page_number == 1
    assert page_review.status_code == 200
    assert page_review.json()["items"] == [{
        "page_number": 1,
        "text_content": "Handbook rule text",
        "content_hash": page.content_hash,
        "extraction_kind": "SELECTABLE_TEXT",
        "review_priority": "NORMAL",
    }]
    assert page_review.json()["next_page_after"] is None
    assert listing.status_code == 200
    assert listing.json()["items"][0]["handbook_id"] == payload["handbook_id"]


def test_handbook_without_selectable_text_requires_manual_review(tmp_path, monkeypatch):
    database_path = tmp_path / "handbook_manual_review.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_handbook",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_handbook"],
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/governance/handbooks",
            data={"domain_id": "dom_handbook"},
            files={"file": ("scanned-handbook.pdf", _blank_pdf(), "application/pdf")},
        )
        handbook_id = response.json()["handbook_id"]
        monkeypatch.setattr(handbook_worker, "AsyncSessionLocal", session_factory)
        extracted = asyncio.run(handbook_worker.process_handbook_upload(handbook_id))

        async def _load_upload():
            async with session_factory() as session:
                return await session.get(DBHandbookUpload, handbook_id)

        upload = asyncio.run(_load_upload())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 201
    assert extracted is False
    assert upload is not None
    assert upload.status == "NEEDS_MANUAL_REVIEW"
    assert "no selectable text" in (upload.error_message or "")


def test_direct_handbook_session_becomes_a_canonical_hashed_source(tmp_path, monkeypatch):
    database_path = tmp_path / "handbook_direct_upload.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    source = _text_pdf()

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    async def _presigned_post(cls, **kwargs):
        assert kwargs["content_type"] == "application/pdf"
        assert kwargs["maximum_size"] == len(source)
        return {"url": "https://storage.example.test/upload", "fields": {"key": kwargs["key"]}}

    async def _object_metadata(cls, _key):
        return {"content_length": len(source), "content_type": "application/pdf"}

    monkeypatch.setattr(BlobStorage, "direct_uploads_available", classmethod(lambda cls: True))
    monkeypatch.setattr(BlobStorage, "create_presigned_post", classmethod(_presigned_post))
    monkeypatch.setattr(BlobStorage, "get_object_metadata", classmethod(_object_metadata))
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_handbook",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_handbook"],
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        session_response = client.post(
            "/api/v1/governance/handbook-upload-sessions",
            json={
                "domain_id": "dom_handbook",
                "file_name": "handbook.pdf",
                "content_type": "application/pdf",
                "file_size_bytes": len(source),
            },
        )
        session_id = session_response.json()["session_id"]

        async def _load_session():
            async with session_factory() as session:
                return await session.get(DBHandbookUploadSession, session_id)

        upload_session = asyncio.run(_load_session())
        assert upload_session is not None
        assert upload_session.storage_key == f"tenants/tenant_handbook/handbook-staging/{session_id}.pdf"
        BlobStorage._store[upload_session.storage_key] = source

        completion = client.post(f"/api/v1/governance/handbook-upload-sessions/{session_id}/complete")
        handbook_id = completion.json()["handbook_id"]
        repeated_completion = client.post(f"/api/v1/governance/handbook-upload-sessions/{session_id}/complete")
        monkeypatch.setattr(handbook_worker, "AsyncSessionLocal", session_factory)
        extracted = asyncio.run(handbook_worker.process_handbook_upload(handbook_id))

        async def _load_upload():
            async with session_factory() as session:
                return await session.get(DBHandbookUpload, handbook_id)

        upload = asyncio.run(_load_upload())
    finally:
        app.dependency_overrides.clear()
        BlobStorage._store.clear()
        asyncio.run(engine.dispose())

    assert session_response.status_code == 201
    assert completion.status_code == 201
    assert completion.json()["content_hash"] is None
    assert repeated_completion.status_code == 409
    assert extracted is True
    assert upload is not None
    assert upload.content_hash == hashlib.sha256(source).hexdigest()
    assert upload.storage_key == f"tenants/tenant_handbook/sources/{upload.content_hash}.pdf"
    assert upload.status == "READY_FOR_REVIEW"


def test_scanned_handbook_ocr_requires_and_records_staff_review(tmp_path, monkeypatch):
    database_path = tmp_path / "handbook_ocr_review.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    async def _candidates(_source_file, **_kwargs):
        return [OCRPageCandidate(page_number=1, text="Verified OCR candidate text", provider_reference="ocr-job-1/page-1")]

    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_handbook",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_handbook"],
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    monkeypatch.setattr(api_module, "ocr_provider_is_configured", lambda: True)
    monkeypatch.setattr(handbook_worker, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(handbook_ocr_worker, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(handbook_ocr_worker, "extract_page_candidates", _candidates)
    try:
        client = TestClient(app)
        uploaded = client.post(
            "/api/v1/governance/handbooks",
            data={"domain_id": "dom_handbook"},
            files={"file": ("scanned-handbook.pdf", _blank_pdf(), "application/pdf")},
        )
        handbook_id = uploaded.json()["handbook_id"]
        extracted = asyncio.run(handbook_worker.process_handbook_upload(handbook_id))
        queued = client.post(f"/api/v1/governance/handbooks/{handbook_id}/ocr")
        ocr_processed = asyncio.run(handbook_ocr_worker.process_handbook_ocr(handbook_id))
        proposals = client.get(f"/api/v1/governance/handbooks/{handbook_id}/ocr-reviews")
        approved = client.patch(
            f"/api/v1/governance/handbooks/{handbook_id}/ocr-reviews/1",
            json={"action": "ACCEPT"},
        )

        async def _load_result():
            async with session_factory() as session:
                upload = await session.get(DBHandbookUpload, handbook_id)
                page = await session.get(DBHandbookPage, f"handbook_page_{handbook_id}_1")
                events = await session.execute(
                    DBHandbookOcrReviewEvent.__table__.select().order_by(DBHandbookOcrReviewEvent.sequence)
                )
                return upload, page, events.fetchall()

        upload, page, events = asyncio.run(_load_result())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert uploaded.status_code == 201
    assert extracted is False
    assert queued.status_code == 202
    assert queued.json()["status"] == "OCR_QUEUED"
    assert ocr_processed is True
    assert proposals.status_code == 200
    assert proposals.json()["items"][0]["status"] == "PENDING_REVIEW"
    assert proposals.json()["items"][0]["proposed_text"] == "Verified OCR candidate text"
    assert len(proposals.json()["items"][0]["source_page_hash"]) == 64
    assert len(proposals.json()["items"][0]["provider_response_hash"]) == 64
    assert proposals.json()["items"][0]["review_priority"] == "NORMAL"
    assert approved.status_code == 200
    assert approved.json()["status"] == "ACCEPTED"
    assert upload is not None and upload.status == "READY_FOR_REVIEW"
    assert page is not None and page.text_content == "Verified OCR candidate text"
    assert [event.action for event in events] == ["PROPOSED", "ACCEPTED"]
