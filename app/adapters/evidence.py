"""
Evidence Adapters.

Proves the architecture is not a monolithic application but a headless engine.
External systems (ERPs, CSV uploads, REST APIs) use Adapters to transform 
their native data formats into our canonical `Evidence` model.
"""

from abc import ABC, abstractmethod
import datetime
from typing import Dict, Any

from app.core.models import Evidence
from app.infrastructure.blob_storage import BlobStorage


class EvidenceAdapter(ABC):
    """Base interface for all data ingestion."""
    
    @abstractmethod
    async def ingest(self, *, tenant_id: str, subject_id: str, raw_payload: Any) -> Evidence:
        """Transforms a domain-specific payload into a canonical Evidence object."""
        pass


class RawTextAdapter(EvidenceAdapter):
    """Adapter for unstructured text (e.g., OCR'd PDFs, user form text)."""
    
    async def ingest(self, *, tenant_id: str, subject_id: str, raw_payload: str) -> Evidence:
        if not isinstance(raw_payload, str):
            raise ValueError("RawTextAdapter expects a string payload.")
            
        import hashlib
        hasher = hashlib.sha256()
        hasher.update(raw_payload.encode("utf-8"))
        content_hash = hasher.hexdigest()

        storage_key = await BlobStorage.upload_text(raw_payload, tenant_id=tenant_id)
        
        return Evidence(
            subject_id=subject_id,
            source_type="user_input",
            storage_key=storage_key,
            cryptographic_hash=content_hash,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )


class LegacyERPAdapter(EvidenceAdapter):
    """
    Mock adapter representing an integration with a legacy system like PeopleSoft or Banner.
    It takes structured JSON from the ERP API and spools it to BlobStorage.
    """
    
    async def ingest(self, *, tenant_id: str, subject_id: str, raw_payload: Dict[str, Any]) -> Evidence:
        if not isinstance(raw_payload, dict):
            raise ValueError("LegacyERPAdapter expects a JSON dictionary payload.")
            
        import json
        stringified_content = json.dumps(raw_payload, sort_keys=True)
        
        import hashlib
        hasher = hashlib.sha256()
        hasher.update(stringified_content.encode("utf-8"))
        content_hash = hasher.hexdigest()
        
        storage_key = await BlobStorage.upload_text(stringified_content, tenant_id=tenant_id)
        
        # We set a high trust level implicitly because it comes from an API
        return Evidence(
            subject_id=subject_id,
            source_type="erp_system",
            storage_key=storage_key,
            cryptographic_hash=content_hash,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
