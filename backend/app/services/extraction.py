"""
Receipt extraction service.

Format-aware pipeline:
  .txt / text-layer PDF  → pypdf text → claude-haiku structured extraction
  image-only PDF / image → Claude vision → structured extraction

Output: ReceiptFields (Pydantic, schema-constrained — never free text parsing).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

from ..config import settings
from .pdf_parser import parse_pdf, parse_text_file

_anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── Schema ────────────────────────────────────────────────────────────────────


class ReceiptFields(BaseModel):
    """Structured fields extracted from a single receipt."""

    vendor: str | None = Field(None, description="Merchant / airline / hotel name")
    category: str | None = Field(
        None,
        description="One of: airfare, lodging, meal, ground_transport, entertainment, other",
    )
    transaction_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    amount: float | None = Field(None, description="Total charged amount (numeric)")
    currency: str = Field("USD", description="3-letter ISO currency code")
    payment_method: str | None = Field(
        None, description="e.g. 'Corporate Visa ****8829', 'Personal card'"
    )

    # Category-specific supplementary fields
    cabin_class: str | None = Field(
        None, description="Airfare only: economy / premium_economy / business / first"
    )
    flight_route: str | None = Field(
        None, description="Airfare: e.g. 'LAX→ORD→LAX'"
    )
    flight_duration_hours: float | None = Field(
        None, description="Airfare: total flight time hours (one-way longest leg)"
    )
    room_rate_per_night: float | None = Field(
        None, description="Lodging: pre-tax nightly room rate"
    )
    num_nights: int | None = Field(None, description="Lodging: number of nights")
    city: str | None = Field(
        None, description="Lodging/meal: city for tier lookup (e.g. 'Chicago')"
    )
    attendees: int | None = Field(
        None, description="Meal/entertainment: number of people"
    )
    extraction_notes: str | None = Field(
        None, description="Anything uncertain or ambiguous"
    )


# ── Extraction prompts ────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = """You are an expense receipt parser for Northwind Logistics.
Extract structured fields from the receipt text/image.
Return ONLY valid JSON matching this schema (omit fields you cannot determine):

{
  "vendor": string or null,
  "category": "airfare"|"lodging"|"meal"|"ground_transport"|"entertainment"|"other" or null,
  "transaction_date": "YYYY-MM-DD" or null,
  "amount": number or null,
  "currency": "USD",
  "payment_method": string or null,
  "cabin_class": "economy"|"premium_economy"|"business"|"first" or null,
  "flight_route": string or null,
  "flight_duration_hours": number or null,
  "room_rate_per_night": number or null,
  "num_nights": integer or null,
  "city": string or null,
  "attendees": integer or null,
  "extraction_notes": string or null
}

Rules:
- amount = total amount actually charged on this receipt (not per-person)
- If a receipt covers multiple nights, set num_nights and room_rate_per_night separately from taxes
- For airfare, set cabin_class based on ticket class codes: Y/B/M = economy, W = premium_economy, C/J = business, F/A = first
- If "Main Cabin" appears, cabin_class = "economy"
- currency defaults to "USD" unless clearly otherwise
- Do not infer or guess fields that are not on the receipt
"""


def _parse_receipt_from_text(receipt_text: str) -> ReceiptFields:
    msg = _anthropic.messages.create(
        model=settings.extraction_model,
        max_tokens=512,
        system=_EXTRACTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Receipt text:\n\n{receipt_text}",
            }
        ],
    )
    return _parse_response(msg.content[0].text)


def _parse_receipt_from_vision(file_bytes: bytes, media_type: str) -> ReceiptFields:
    """Use Claude vision to extract fields directly from image/PDF bytes."""
    b64 = base64.standard_b64encode(file_bytes).decode()

    if media_type == "application/pdf":
        source = {
            "type": "base64",
            "media_type": "application/pdf",
            "data": b64,
        }
        content_item: dict = {"type": "document", "source": source}
    else:
        source = {"type": "base64", "media_type": media_type, "data": b64}
        content_item = {"type": "image", "source": source}

    msg = _anthropic.messages.create(
        model=settings.reasoning_model,
        max_tokens=512,
        system=_EXTRACTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    content_item,
                    {"type": "text", "text": "Extract all receipt fields as JSON."},
                ],
            }
        ],
    )
    return _parse_response(msg.content[0].text)


def _parse_response(raw: str) -> ReceiptFields:
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return ReceiptFields()
    try:
        data = json.loads(raw[start:end])
        return ReceiptFields(**{k: v for k, v in data.items() if k in ReceiptFields.model_fields})
    except Exception:
        return ReceiptFields(extraction_notes=f"Parse error: {raw[:200]}")


# ── Public API ────────────────────────────────────────────────────────────────

_MIN_TEXT_CHARS = 80  # below this, treat PDF as image-only


def extract_receipt(filename: str, content: bytes) -> ReceiptFields:
    """
    Main entry: infer format from filename and content, dispatch to
    text extraction or vision.
    """
    name = filename.lower()
    suffix = Path(name).suffix

    if suffix == ".txt":
        text = parse_text_file(content)
        return _parse_receipt_from_text(text)

    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        mt_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".gif": "image/gif", ".webp": "image/webp"}
        return _parse_receipt_from_vision(content, mt_map[suffix])

    # PDF — try text layer first
    if suffix == ".pdf":
        try:
            text = parse_pdf(content, filename)
        except Exception:
            text = ""
        if len(text.strip()) >= _MIN_TEXT_CHARS:
            return _parse_receipt_from_text(text)
        else:
            return _parse_receipt_from_vision(content, "application/pdf")

    # Unknown format — try text, fall back to vision
    try:
        text = content.decode("utf-8", errors="replace")
        if len(text.strip()) >= _MIN_TEXT_CHARS:
            return _parse_receipt_from_text(text)
    except Exception:
        pass
    return _parse_receipt_from_vision(content, "application/octet-stream")
