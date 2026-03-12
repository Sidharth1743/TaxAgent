"""Document extraction for tax forms using Document AI and Gemini Vision.

Supports W-2, 1099 (US) and Form 16 (India) with automatic fallback
from Document AI Form Parser to Gemini Vision extraction.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import List

import structlog
from pydantic import BaseModel

from config import (
    DOCAI_LOCATION,
    DOCAI_PROCESSOR_ID,
    GOOGLE_API_KEY,
    SPANNER_PROJECT_ID,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FormField(BaseModel):
    name: str
    value: str
    confidence: float


class ExtractedDocument(BaseModel):
    doc_id: str
    form_type: str
    fields: List[FormField]
    jurisdiction: str
    raw_text: str


# ---------------------------------------------------------------------------
# Form type detection
# ---------------------------------------------------------------------------

_FORM_PATTERNS = {
    "w2": [r"w[\-_\s]?2", r"wage\s+and\s+tax"],
    "1099": [r"1099"],
    "form16": [r"form[\-_\s]?16", r"form\s+no\.?\s*16"],
}


def detect_form_type(filename: str, text_hint: str = "") -> str:
    """Return 'w2', '1099', 'form16', or 'unknown' based on filename and content."""
    combined = f"{filename} {text_hint}".lower()
    for form_type, patterns in _FORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, combined):
                return form_type
    return "unknown"


# ---------------------------------------------------------------------------
# Field specs per form type (for Gemini Vision prompts)
# ---------------------------------------------------------------------------

_FIELD_SPECS = {
    "w2": [
        "employer_name", "employer_ein", "wages",
        "federal_tax_withheld", "state_tax_withheld",
        "social_security_wages", "medicare_wages",
    ],
    "1099": [
        "payer_name", "payer_tin", "income_amount",
        "federal_tax_withheld",
    ],
    "form16": [
        "employer_name", "employer_tan", "pan",
        "gross_salary", "total_deductions", "taxable_income",
        "tax_payable", "tds_deducted",
    ],
}


# ---------------------------------------------------------------------------
# Document AI extraction
# ---------------------------------------------------------------------------

async def extract_with_docai(file_bytes: bytes, mime_type: str) -> List[FormField]:
    """Extract form fields using Google Document AI Form Parser."""
    from google.cloud import documentai_v1 as documentai

    processor_name = (
        f"projects/{SPANNER_PROJECT_ID}/locations/{DOCAI_LOCATION}"
        f"/processors/{DOCAI_PROCESSOR_ID}"
    )

    client = documentai.DocumentProcessorServiceAsyncClient()
    raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

    logger.info("docai_extraction_start", processor=processor_name)
    result = await client.process_document(request=request)
    document = result.document

    fields: List[FormField] = []
    for page in document.pages:
        for form_field in page.form_fields:
            field_name = _get_text(form_field.field_name, document.text).strip()
            field_value = _get_text(form_field.field_value, document.text).strip()
            confidence = form_field.field_value.confidence if form_field.field_value else 0.0
            if field_name:
                fields.append(FormField(
                    name=field_name,
                    value=field_value,
                    confidence=confidence,
                ))

    logger.info("docai_extraction_done", field_count=len(fields))
    return fields


def _get_text(layout, full_text: str) -> str:
    """Extract text from a Document AI layout element using text anchors."""
    if not layout or not layout.text_anchor or not layout.text_anchor.text_segments:
        return ""
    parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index) if segment.end_index else 0
        parts.append(full_text[start:end])
    return "".join(parts)


# ---------------------------------------------------------------------------
# Gemini Vision extraction
# ---------------------------------------------------------------------------

async def extract_with_gemini_vision(
    file_bytes: bytes, mime_type: str, form_type: str
) -> List[FormField]:
    """Extract form fields using Gemini Vision (multimodal)."""
    from google import genai

    field_names = _FIELD_SPECS.get(form_type, _FIELD_SPECS["w2"])
    fields_json = json.dumps(field_names)

    prompt = (
        f"Extract the following fields from this tax document: {fields_json}.\n"
        "Return ONLY a JSON array of objects with keys: "
        '"name" (field name), "value" (extracted value as string).\n'
        "If a field is not found, omit it. Do not include any explanation."
    )

    client = genai.Client(api_key=GOOGLE_API_KEY)

    # Build inline data part for the document
    inline_data = genai.types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

    logger.info("gemini_vision_extraction_start", form_type=form_type)
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash-preview-05-20",
        contents=[inline_data, prompt],
    )

    # Parse JSON from response
    text = response.text or ""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")

    fields: List[FormField] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in parsed:
                fields.append(FormField(
                    name=item.get("name", ""),
                    value=str(item.get("value", "")),
                    confidence=0.85,
                ))
    except json.JSONDecodeError:
        logger.warning("gemini_vision_json_parse_error", raw=text[:200])

    logger.info("gemini_vision_extraction_done", field_count=len(fields))
    return fields


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def extract_document(
    file_bytes: bytes, filename: str, mime_type: str
) -> ExtractedDocument:
    """Detect form type, extract fields via Document AI or Gemini Vision."""
    form_type = detect_form_type(filename)
    jurisdiction = "usa" if form_type in ("w2", "1099") else ("india" if form_type == "form16" else "unknown")

    logger.info(
        "extract_document_start",
        filename=filename,
        form_type=form_type,
        jurisdiction=jurisdiction,
    )

    fields: List[FormField] = []

    # Try Document AI first for US forms if processor is configured
    use_docai = bool(DOCAI_PROCESSOR_ID) and jurisdiction == "usa"
    if use_docai:
        try:
            fields = await extract_with_docai(file_bytes, mime_type)
        except Exception as exc:
            logger.warning("docai_fallback_to_gemini", error=str(exc))
            fields = []

    # Fall back to Gemini Vision if no fields from Document AI
    if not fields:
        try:
            fields = await extract_with_gemini_vision(file_bytes, mime_type, form_type)
        except Exception as exc:
            logger.error("gemini_vision_extraction_failed", error=str(exc))

    raw_text = ""  # Could be populated from Document AI response if needed

    doc_id = uuid.uuid4().hex

    return ExtractedDocument(
        doc_id=doc_id,
        form_type=form_type,
        fields=fields,
        jurisdiction=jurisdiction,
        raw_text=raw_text,
    )
