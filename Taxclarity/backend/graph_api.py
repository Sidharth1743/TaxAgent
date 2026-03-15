"""Graph API service for document upload, extraction, and SQL-backed memory storage.

Runs on port 8006. Provides REST endpoints for uploading tax documents,
retrieving extracted data, and confirming/storing in Spanner graph.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import configure_logging

configure_logging()

from agents.calculation_agent import compute_tax_liability  # noqa: E402
from backend.document_extractor import ExtractedDocument, extract_document  # noqa: E402
from backend.obsidian_graph import build_obsidian_graph  # noqa: E402
from memory.memory_service import get_memory_service  # noqa: E402
from memory.spanner_graph import analyze_insights, fetch_user_graph  # noqa: E402

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="TaxAgent Graph API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# In-memory document store (upload -> confirm flow)
# ---------------------------------------------------------------------------

_document_store: Dict[str, ExtractedDocument] = {}


def get_graph_database():
    """Compatibility shim for tests and older callers.

    Returns None in the SQL-backed path unless patched by tests.
    """
    return None


_W2_CANONICAL_PATTERNS: Dict[str, List[str]] = {
    "wages": [
        r"\bbox\s*1\b",
        r"^\s*1[\s\.\-:]*wages",
        r"wages,\s*tips,\s*other\s*compensation",
    ],
    "federal_tax_withheld": [
        r"\bbox\s*2\b",
        r"^\s*2[\s\.\-:]*federal",
        r"federal\s+income\s+tax\s+withheld",
    ],
    "social_security_wages": [
        r"\bbox\s*3\b",
        r"^\s*3[\s\.\-:]*social\s+security\s+wages",
        r"social\s+security\s+wages",
    ],
    "medicare_wages": [
        r"\bbox\s*5\b",
        r"^\s*5[\s\.\-:]*medicare\s+wages",
        r"medicare\s+wages",
    ],
    "state_tax_withheld": [
        r"\bbox\s*17\b",
        r"^\s*17[\s\.\-:]*state\s+income\s+tax",
        r"state\s+income\s+tax",
    ],
    "employer_ein": [
        r"\bbox\s*b\b",
        r"employer'?s?\s+identification\s+number",
        r"\bein\b",
    ],
}


def _normalize_w2_compute_fields(fields: Dict[str, str]) -> Dict[str, str]:
    """Map raw W-2 extractor labels to canonical compute field names."""
    normalized = dict(fields)

    for canonical_key, patterns in _W2_CANONICAL_PATTERNS.items():
        existing_value = normalized.get(canonical_key)
        if existing_value not in (None, ""):
            continue

        for raw_key, raw_value in fields.items():
            if raw_value in (None, ""):
                continue

            key_text = raw_key.lower().strip()
            if any(re.search(pattern, key_text) for pattern in patterns):
                normalized[canonical_key] = raw_value
                break

    return normalized


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class ConfirmRequest(BaseModel):
    user_id: str
    corrections: Optional[Dict[str, str]] = None


class ConfirmResponse(BaseModel):
    doc_id: str
    spanner_stored: bool
    form_id: Optional[str] = None
    entity_ids: Optional[List[str]] = None
    jurisdiction_id: Optional[str] = None


class ComputeRequest(BaseModel):
    filing_status: Optional[str] = "single"  # for US tax
    additional_deductions: Optional[Dict[str, int]] = None  # for India 80C/80D/etc


class ComputeResponse(BaseModel):
    doc_id: str
    form_type: str
    jurisdiction: str
    computation: Dict[str, Any]


# ---------------------------------------------------------------------------
# Graph visualization models
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    color: str


class GraphLink(BaseModel):
    source: str
    target: str
    type: str


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


class InsightItem(BaseModel):
    type: str
    message: str
    section: Optional[str] = None
    potential_savings: Optional[str] = None


# ---------------------------------------------------------------------------
# Graph endpoints
# ---------------------------------------------------------------------------

@app.get("/api/graph/{user_id}", response_model=GraphResponse)
async def get_user_graph(user_id: str, session_id: Optional[str] = None):
    """Return D3-compatible graph data for a user."""
    obsidian_result = build_obsidian_graph(user_id, session_id=session_id)
    if session_id is not None:
        return GraphResponse(nodes=obsidian_result["nodes"], links=[
            {
                "source": edge["from"],
                "target": edge["to"],
                "type": edge["type"],
            }
            for edge in obsidian_result["edges"]
        ])
    if obsidian_result.get("nodes"):
        return GraphResponse(nodes=obsidian_result["nodes"], links=[
            {
                "source": edge["from"],
                "target": edge["to"],
                "type": edge["type"],
            }
            for edge in obsidian_result["edges"]
        ])
    graph_db = get_graph_database()
    if graph_db is not None:
        result = fetch_user_graph(graph_db, user_id)
    else:
        result = await get_memory_service().fetch_graph(user_id)
    return GraphResponse(**result)


@app.get("/api/graph/{user_id}/insights", response_model=List[InsightItem])
async def get_user_insights(user_id: str):
    """Return proactive deduction gap suggestions for a user."""
    graph_db = get_graph_database()
    if graph_db is not None:
        return analyze_insights(graph_db, user_id)
    return await get_memory_service().fetch_insights(user_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile):
    """Upload a tax document (PDF or image) and extract fields."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content_type = file.content_type or "application/pdf"
    file_bytes = await file.read()

    logger.info("document_upload", filename=file.filename, size=len(file_bytes))

    doc = await extract_document(file_bytes, file.filename, content_type)
    _document_store[doc.doc_id] = doc

    logger.info("document_extracted", doc_id=doc.doc_id, form_type=doc.form_type, field_count=len(doc.fields))

    result = doc.model_dump()
    result["pageindex_doc_id"] = None
    return result


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """Retrieve previously extracted document data."""
    doc = _document_store.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc.model_dump()


@app.post("/api/documents/{doc_id}/confirm", response_model=ConfirmResponse)
async def confirm_document(doc_id: str, body: ConfirmRequest):
    """Confirm extracted data (with optional corrections) and store in Spanner."""
    doc = _document_store.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Apply corrections
    if body.corrections:
        for field in doc.fields:
            if field.name in body.corrections:
                field.value = body.corrections[field.name]
                field.confidence = 1.0  # User-corrected = full confidence
        logger.info("corrections_applied", doc_id=doc_id, count=len(body.corrections))

    # Store structured document state in SQL-backed memory service
    try:
        result = await get_memory_service().store_document_memory(
            user_id=body.user_id,
            doc_id=doc_id,
            filename=f"{doc.form_type}_{doc_id}",
            form_type=doc.form_type,
            jurisdiction=doc.jurisdiction,
            raw_payload=doc.raw_payload or {},
            raw_text=doc.raw_text,
            fields=[f.model_dump() for f in doc.fields],
            tables=doc.tables or [],
            confirmed=True,
        )

        logger.info("document_stored_in_memory_service", doc_id=doc_id, result=result)
        return ConfirmResponse(
            doc_id=doc_id,
            spanner_stored=True,
            form_id=result.get("form_id"),
            entity_ids=result.get("entity_ids"),
            jurisdiction_id=result.get("jurisdiction_id"),
        )

    except Exception as exc:
        logger.error("document_storage_failed", doc_id=doc_id, error=str(exc))
        return ConfirmResponse(doc_id=doc_id, spanner_stored=False)


@app.post("/api/documents/{doc_id}/compute", response_model=ComputeResponse)
async def compute_tax(doc_id: str, body: ComputeRequest = ComputeRequest()):
    """Compute tax liability from a previously extracted document."""
    doc = _document_store.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Convert fields list to dict
    persisted_fields = await get_memory_service().fetch_document_fields(doc_id)
    fields_dict: Dict[str, str] = persisted_fields or {f.name: f.value for f in doc.fields}
    if doc.form_type.lower() in {"w2", "w-2"} or doc.jurisdiction.lower() in {"us", "usa"}:
        fields_dict = _normalize_w2_compute_fields(fields_dict)

    # Merge additional deductions if provided
    if body.additional_deductions:
        for key, val in body.additional_deductions.items():
            fields_dict[key] = str(val)

    # For US forms, pass filing_status through
    if body.filing_status and body.filing_status != "single":
        fields_dict["filing_status"] = body.filing_status

    result = compute_tax_liability(fields_dict, doc.form_type, doc.jurisdiction)

    logger.info("tax_computed", doc_id=doc_id, form_type=doc.form_type, jurisdiction=doc.jurisdiction)

    return ComputeResponse(
        doc_id=doc_id,
        form_type=doc.form_type,
        jurisdiction=doc.jurisdiction,
        computation=result,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from config import GRAPH_API_PORT  # noqa: E402

    uvicorn.run(app, host="0.0.0.0", port=GRAPH_API_PORT)
