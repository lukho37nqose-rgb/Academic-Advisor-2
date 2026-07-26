"""
LLM Gateway.

The ONLY place in the entire system that imports AI libraries or knows 
about OpenAI, Anthropic, or Mock providers.
All calls must be asynchronous to prevent blocking the FastAPI event loop.
"""

import os
import json
from typing import Dict, Any, Optional, Type, TypeVar, cast
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel
from app.services.ai_safety import configured_ai_provider, validate_external_ai_processing_configuration

T = TypeVar("T", bound=BaseModel)

# We create an instructor-patched async client for reliable JSON extraction
def get_async_client() -> Optional[instructor.AsyncInstructor]:
    """Returns an external client only after the data-boundary gate passes."""
    if configured_ai_provider() == "mock":
        return None
    validate_external_ai_processing_configuration()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("External AI processing requires OPENAI_API_KEY.")
    return instructor.from_openai(AsyncOpenAI(api_key=api_key))


async def extract_with_instructor(raw_text: str, response_model: Type[T]) -> T:
    """
    Asynchronously calls the LLM to extract data mapping strictly to the provided Pydantic model.
    Uses Instructor to strictly enforce the shape.
    """
    client = get_async_client()
    
    # If no API key, gracefully fallback to a mock return (fails if it can't be cast)
    if not client:
        # For mocking locally, if the response_model has a mock_data classmethod, use it.
        if hasattr(response_model, 'mock_data'):
            return response_model.mock_data() # type: ignore
        raise ValueError("Cannot mock LLM extraction without a mock_data classmethod on the response model.")
            
    response = await client.chat.completions.create(
        model="gpt-4o",
        response_model=response_model,
        messages=[
            {"role": "system", "content": "You are a precise data extraction AI. Extract the requested information from the text exactly according to the schema. Always include source citations if requested."},
            {"role": "user", "content": raw_text}
        ]
    )
    
    return response


async def call_structured_extraction(raw_text: str, schema_definition: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy endpoint. Will be deprecated in favor of `extract_with_instructor`."""
    client = get_async_client()
    if not client:
        try: return json.loads(raw_text)
        except json.JSONDecodeError: return {}
            
    openai_client = cast(Any, client.client)
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"Extract the following data from the user text. You MUST return a valid JSON object matching this schema exactly: {json.dumps(schema_definition)}. Do not include any other text."},
            {"role": "user", "content": raw_text}
        ]
    )
    try: return json.loads(response.choices[0].message.content) # type: ignore
    except Exception as e: raise ValueError(f"LLM Extraction failed: {str(e)}")
