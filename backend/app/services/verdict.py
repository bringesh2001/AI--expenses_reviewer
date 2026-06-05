"""
Per-item verdict pipeline.

Pass 1 (this module): one verdict per line item
Pass 2 (pipeline.py): cross-item rules (duplicates, daily meal totals, approval threshold)

Verdict gate (deterministic post-processing):
  1. Faithfulness  — cited text must be a substring of the source chunk text
  2. Grounding     — non-compliant verdicts require ≥1 verified citation
  3. Score floor   — best retrieval score must clear min_retrieval_score
  4. Confidence    — floor = min(model_confidence, retrieval_conf, citation_conf)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel, Field

from ..config import settings
from .retrieval import ChunkResult, hybrid_search
from .extraction import ReceiptFields
from sqlalchemy.ext.asyncio import AsyncSession

_anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── Verdict schemas ───────────────────────────────────────────────────────────


class VerdictCitation(BaseModel):
    chunk_id: str
    policy_id: str
    section: str
    text: str          # verbatim excerpt from the policy chunk
    score: float


class VerdictResult(BaseModel):
    verdict: str = Field(description="compliant|flagged|needs_review|rejected")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    citations: list[VerdictCitation]
    retrieval_score: float
    gate_applied: str | None = None  # which gate downgraded the verdict, if any


# ── Reasoning prompt ──────────────────────────────────────────────────────────

_VERDICT_SYSTEM = """You are the AI pre-reviewer for Northwind Logistics travel & expense submissions.
Your role is to evaluate whether a single expense line item complies with company policy.

You are given:
- Employee context: grade, department (frozen at submission time)
- Expense details: category, vendor, amount, date, and category-specific fields
- Relevant policy excerpts (retrieved for this specific expense)

Return ONLY valid JSON with this schema:
{
  "verdict": "compliant" | "flagged" | "needs_review" | "rejected",
  "confidence": <0.0–1.0>,
  "reasoning": "<2-4 sentences explaining the verdict, citing specific policy numbers>",
  "citations": [
    {
      "chunk_id": "<id from the policy excerpts>",
      "policy_id": "<TEP-XXX>",
      "section": "<§N.N>",
      "text": "<verbatim excerpt from the policy that supports your verdict>",
      "score": <0.0–1.0>
    }
  ]
}

Verdict definitions:
- compliant:    Policy allows the expense with no conditions unmet
- flagged:      Technically within policy but warrants attention (near limit, unusual pattern)
- needs_review: Cannot determine compliance without more information
- rejected:     Policy clearly prohibits this expense as submitted

Confidence guidelines:
- 0.9+: Clear rule, exact numbers match or mismatch unambiguously
- 0.7–0.9: Rule applies but depends on interpretation or missing details
- 0.5–0.7: Multiple rules may apply, or rule wording is ambiguous
- <0.5: Use needs_review instead of guessing

Important:
- Do NOT invent policy rules. If no policy excerpt covers the expense, return needs_review.
- For "rejected", you MUST include at least one citation with the specific violated rule.
- For "compliant", cite the rule that permits the expense.
- Quote the specific dollar limits from the policy text (e.g. "$250/night", "$75 solo dinner").
"""

VERDICTS_REQUIRING_CITATION = {"rejected", "flagged"}
VERDICTS_DOWNGRADE_TO = "needs_review"


def _build_item_context(fields: ReceiptFields, snapshot_grade: int, snapshot_department: str) -> str:
    parts = [
        f"Employee grade: {snapshot_grade}",
        f"Employee department: {snapshot_department}",
        f"Category: {fields.category or 'unknown'}",
        f"Vendor: {fields.vendor or 'unknown'}",
        f"Amount: ${fields.amount:.2f}" if fields.amount else "Amount: unknown",
        f"Date: {fields.transaction_date or 'unknown'}",
        f"Payment: {fields.payment_method or 'unknown'}",
    ]
    if fields.cabin_class:
        parts.append(f"Cabin class: {fields.cabin_class}")
    if fields.flight_route:
        parts.append(f"Route: {fields.flight_route}")
    if fields.flight_duration_hours:
        parts.append(f"Flight duration: {fields.flight_duration_hours:.1f}h")
    if fields.room_rate_per_night:
        parts.append(f"Room rate/night: ${fields.room_rate_per_night:.2f}")
    if fields.num_nights:
        parts.append(f"Nights: {fields.num_nights}")
    if fields.city:
        parts.append(f"City: {fields.city}")
    if fields.attendees:
        parts.append(f"Attendees: {fields.attendees}")
    if fields.extraction_notes:
        parts.append(f"Notes: {fields.extraction_notes}")
    return "\n".join(parts)


def _build_policy_context(chunks: list[ChunkResult]) -> str:
    return "\n\n---\n\n".join(
        f"[chunk_id={c.chunk_id}] [{c.policy_id} {c.section}] {c.title}\n{c.text}"
        for c in chunks
    )


def _call_llm(item_context: str, policy_context: str) -> dict:
    user_msg = (
        f"Expense line item:\n{item_context}\n\n"
        f"Relevant policy excerpts:\n{policy_context}\n\n"
        "Return the verdict JSON."
    )
    msg = _anthropic.messages.create(
        model=settings.reasoning_model,
        max_tokens=1024,
        system=_VERDICT_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ── Verdict gate ──────────────────────────────────────────────────────────────


def _faithfulness_check(citations: list[dict], chunk_map: dict[str, ChunkResult]) -> float:
    """
    Fraction of citations whose cited text is a substring of the source chunk.
    Returns 1.0 if no citations.
    """
    if not citations:
        return 1.0
    passed = 0
    for cit in citations:
        chunk = chunk_map.get(cit.get("chunk_id", ""))
        if chunk and cit.get("text", "").lower() in chunk.text.lower():
            passed += 1
    return passed / len(citations)


def _apply_gate(
    verdict: str,
    model_confidence: float,
    citations: list[dict],
    chunk_map: dict[str, ChunkResult],
    best_retrieval_score: float,
) -> VerdictResult:
    gate_applied: str | None = None

    # Gate 1: Retrieval score floor
    if best_retrieval_score < settings.min_retrieval_score:
        verdict = "needs_review"
        model_confidence = min(model_confidence, 0.4)
        gate_applied = "low_retrieval_score"

    # Gate 2: Faithfulness
    faithfulness = _faithfulness_check(citations, chunk_map)
    citation_conf = faithfulness  # 1.0 = all citations verified

    # Gate 3: Grounding — non-compliant without citation → needs_review
    if verdict in VERDICTS_REQUIRING_CITATION and not citations:
        verdict = VERDICTS_DOWNGRADE_TO
        gate_applied = "missing_citation"

    # Gate 4: Confidence floor = min(model, retrieval_permitted, citation_permitted)
    retrieval_conf = min(1.0, best_retrieval_score / 0.85)  # normalise to 0–1
    confidence = min(model_confidence, retrieval_conf, citation_conf)
    confidence = max(confidence, 0.0)

    if confidence < settings.min_confidence:
        verdict = "needs_review"
        gate_applied = gate_applied or "low_confidence"

    return VerdictResult(
        verdict=verdict,
        confidence=round(confidence, 3),
        reasoning="",  # filled by caller
        citations=[VerdictCitation(**{k: c[k] for k in VerdictCitation.model_fields if k in c}) for c in citations],
        retrieval_score=round(best_retrieval_score, 3),
        gate_applied=gate_applied,
    )


# ── Public API ────────────────────────────────────────────────────────────────


async def compute_verdict(
    fields: ReceiptFields,
    snapshot_grade: int,
    snapshot_department: str,
    db: AsyncSession,
) -> VerdictResult:
    """Retrieve policy chunks, call LLM, apply gate, return VerdictResult."""

    # Build a retrieval query from the receipt fields
    query_parts = [fields.category or "", fields.vendor or ""]
    if fields.city:
        query_parts.append(fields.city)
    if fields.cabin_class:
        query_parts.append(f"cabin class {fields.cabin_class}")
    if fields.amount:
        query_parts.append(f"${fields.amount:.2f}")
    query = " ".join(p for p in query_parts if p).strip()
    if not query:
        query = "expense reimbursement policy"

    # Category → domain filter
    domain_map = {
        "airfare": ["airfare", "air_travel", "cabin_class"],
        "lodging": ["lodging", "hotel", "tier"],
        "meal": ["meals", "per_diem"],
        "ground_transport": ["ground_transport"],
        "entertainment": ["entertainment", "gifts"],
    }
    domain_filter = domain_map.get(fields.category or "", None)

    chunks = await hybrid_search(query, db, domain_filter=domain_filter)

    best_score = chunks[0].final_score if chunks else 0.0
    chunk_map = {c.chunk_id: c for c in chunks}

    if not chunks:
        return VerdictResult(
            verdict="needs_review",
            confidence=0.0,
            reasoning="No policy chunks retrieved; cannot evaluate compliance.",
            citations=[],
            retrieval_score=0.0,
            gate_applied="no_retrieval",
        )

    # LLM reasoning
    item_ctx = _build_item_context(fields, snapshot_grade, snapshot_department)
    policy_ctx = _build_policy_context(chunks)

    try:
        data = _call_llm(item_ctx, policy_ctx)
    except Exception as e:
        return VerdictResult(
            verdict="needs_review",
            confidence=0.0,
            reasoning=f"LLM error: {e}",
            citations=[],
            retrieval_score=best_score,
            gate_applied="llm_error",
        )

    verdict_str = data.get("verdict", "needs_review")
    model_conf = float(data.get("confidence", 0.5))
    reasoning = data.get("reasoning", "")
    raw_citations = data.get("citations", [])

    # Apply gate
    result = _apply_gate(verdict_str, model_conf, raw_citations, chunk_map, best_score)
    result.reasoning = reasoning

    return result
