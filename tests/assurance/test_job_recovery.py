from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBHandbookPage, DBHandbookUpload
from app.infrastructure.repositories import HandbookRepository
from app.services import handbook_worker
from app.services.auth import Role, UserIdentity, get_current_user


class SimulatedWorkerTermination(BaseException):
    """Represents a process termination that bypasses normal error handling."""


def _three_page_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for page_number in range(1, 4):
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
        stream.set_data(f"BT /F1 12 Tf 72 720 Td (Handbook page {page_number}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def test_handbook_worker_resumes_after_an_abrupt_interruption(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "handbook_recovery.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    source = _three_page_pdf()

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def test_db_session():
        async with session_factory() as session:
            yield session

    async def load_upload(handbook_id: str):
        async with session_factory() as session:
            upload = await session.get(DBHandbookUpload, handbook_id)
            pages = (await session.execute(
                select(DBHandbookPage).where(DBHandbookPage.handbook_id == handbook_id).order_by(DBHandbookPage.page_number)
            )).scalars().all()
            return upload, pages

    asyncio.run(create_schema())
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_assurance",
        role=Role.RULE_AUTHOR,
        user_id="author_1",
        domain_ids=["dom_assurance"],
    )
    app.dependency_overrides[get_db_session] = test_db_session
    monkeypatch.setattr(handbook_worker, "AsyncSessionLocal", session_factory)
    original_save_page = HandbookRepository.save_page

    async def interrupted_save_page(self, **kwargs):
        if kwargs["page_number"] == 2:
            raise SimulatedWorkerTermination()
        await original_save_page(self, **kwargs)

    try:
        with TestClient(app) as client:
            uploaded = client.post(
                "/api/v1/governance/handbooks",
                data={"domain_id": "dom_assurance"},
                files={"file": ("large-handbook.pdf", source, "application/pdf")},
            )
        handbook_id = uploaded.json()["handbook_id"]
        monkeypatch.setattr(HandbookRepository, "save_page", interrupted_save_page)
        with pytest.raises(SimulatedWorkerTermination):
            asyncio.run(handbook_worker.process_handbook_upload(handbook_id))
        interrupted_upload, interrupted_pages = asyncio.run(load_upload(handbook_id))

        monkeypatch.setattr(HandbookRepository, "save_page", original_save_page)
        resumed = asyncio.run(handbook_worker.process_handbook_upload(handbook_id))
        completed_upload, completed_pages = asyncio.run(load_upload(handbook_id))
    finally:
        app.dependency_overrides.clear()
        BlobStorage._store.clear()
        asyncio.run(engine.dispose())

    assert uploaded.status_code == 201
    assert interrupted_upload is not None
    assert interrupted_upload.status == "EXTRACTING"
    assert interrupted_upload.processed_pages == 1
    assert [page.page_number for page in interrupted_pages] == [1]
    assert resumed is True
    assert completed_upload is not None
    assert completed_upload.status == "READY_FOR_REVIEW"
    assert completed_upload.processed_pages == 3
    assert [page.page_number for page in completed_pages] == [1, 2, 3]
    assert len({page.content_hash for page in completed_pages}) == 3
    assert completed_upload.content_hash == hashlib.sha256(source).hexdigest()
