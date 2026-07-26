import logging
from typing import AsyncGenerator, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from .models import Claim
from app.services.llm_gateway import extract_with_instructor
from app.services.ai_safety import external_ai_max_input_bytes, external_ai_processing_enabled

logger = logging.getLogger(__name__)

class ExtractedClaim(BaseModel):
    """Pydantic model used strictly by the LLM via Instructor to guarantee shape."""
    target_path: str = Field(description="The domain variable being extracted, e.g., 'academic.gpa'")
    asserted_value: Any = Field(description="The extracted value.")
    source_quote: str = Field(description="Exact quote from the text supporting this value.")
    is_ambiguous: bool = Field(description="True if the text is messy, contradictory, or hard to confidently extract.")
    extraction_confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the extraction accuracy (0.0 to 1.0).")

class ExtractedClaimsPayload(BaseModel):
    claims: List[ExtractedClaim]
    
    @classmethod
    def mock_data(cls):
        """Used for local development without OpenAI keys."""
        return cls(claims=[
            ExtractedClaim(
                target_path="mock.path", 
                asserted_value="Extracted claim from evidence.", 
                source_quote="Mock quote.", 
                is_ambiguous=False, 
                extraction_confidence=0.9
            )
        ])

class EvidenceExtractor:
    def __init__(self, evidence_id: str = "unknown"):
        self.evidence_id = evidence_id
        self.max_bytes = 5 * 1024 * 1024 # 5MB limit
        self.external_ai_max_bytes = external_ai_max_input_bytes()
        
    async def extract_claims_from_stream(self, evidence_stream: AsyncGenerator[bytes, None]) -> list[Claim]:
        """
        Reads evidence from an async stream and extracts claims.
        Handles the ambiguity protocol if parsing is complex.
        Safely enforces file size limits.
        """
        buffer = bytearray()
        total_bytes = 0
        
        async for chunk in evidence_stream:
            total_bytes += len(chunk)
            if total_bytes > self.max_bytes:
                # Handle large files safely instead of silently truncating
                logger.warning(f"Evidence exceeds maximum size of {self.max_bytes} bytes. Emitting Needs Review claim.")
                return [Claim(
                    id="system-truncation-claim",
                    evidence_id=self.evidence_id,
                    target_path="system.file_size",
                    asserted_value=f"Evidence file size ({total_bytes} bytes) exceeds maximum limit ({self.max_bytes} bytes).",
                    extraction_confidence=1.0,
                    source_trust_level=1.0
                )]
            if external_ai_processing_enabled() and total_bytes > self.external_ai_max_bytes:
                logger.warning("Evidence exceeds the approved external AI input limit. Emitting Needs Review claim.")
                return [Claim(
                    id="system-external-ai-limit-claim",
                    evidence_id=self.evidence_id,
                    target_path="system.external_ai_input_size",
                    asserted_value=(
                        f"Evidence file size ({total_bytes} bytes) exceeds the approved external AI input limit "
                        f"({self.external_ai_max_bytes} bytes)."
                    ),
                    extraction_confidence=1.0,
                    source_trust_level=1.0,
                    status="needs_human_review",
                )]
            buffer.extend(chunk)
            
        text_content = buffer.decode("utf-8", errors="replace")
        
        if not text_content.strip():
             return []
             
        # Call the LLM Gateway using Instructor for guaranteed Pydantic models
        llm_payload: ExtractedClaimsPayload = await extract_with_instructor(
            raw_text=text_content, 
            response_model=ExtractedClaimsPayload
        )
        
        canonical_claims = []
        for c in llm_payload.claims:
            status: Literal["resolved", "needs_human_review"] = "needs_human_review" if c.is_ambiguous else "resolved"
            
            canonical_claims.append(Claim(
                evidence_id=self.evidence_id,
                target_path=c.target_path,
                asserted_value=c.asserted_value,
                extraction_confidence=c.extraction_confidence,
                source_trust_level=0.9, # In reality, derived from Evidence Source Type
                status=status,
                source_quote=c.source_quote,
            ))
            
        return canonical_claims
