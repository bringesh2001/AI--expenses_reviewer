"""
Policy Q&A service.

Pipeline:
1. Scope gate — classify question as in_scope / out_of_scope using claude-haiku
2. Hybrid retrieval (retrieval.py)
3. Retrieval confidence check — if best score < threshold, decline
4. Answer generation — claude-sonnet with retrieved context + citation schema
5. Persist QASession
"""
from __future__ import annotations

import uuid

import anthropic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.qa_session import QASession, QAStatus
from .retrieval import hybrid_search, ChunkResult

_anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── Pydantic schemas for LLM output ──────────────────────────────────────────


class CitationSchema(BaseModel):
    chunk_id: str
    policy_id: str
    section: str
    text: str
    score: float


class QAAnswerSchema(BaseModel):
    answer: str
    confidence: float
    citations: list[CitationSchema]


# ── Scope gate ────────────────────────────────────────────────────────────────

SCOPE_SYSTEM = (
    "You are a classifier for a corporate travel & expense policy assistant. "
    "Determine whether the user's question is answerable from Northwind Logistics "
    "travel & expense policies (TEP-001 through TEP-012). "
    "These policies cover: airfare, lodging, meals, alcohol, per-diem rates, "
    "receipt requirements, employee grades, corporate cards, and gifts/entertainment. "
    "Return ONLY one word: IN_SCOPE or OUT_OF_SCOPE."
)


def _is_in_scope(question: str) -> bool:
    msg = _anthropic.messages.create(
        model=settings.extraction_model,
        max_tokens=10,
        system=SCOPE_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    return "IN_SCOPE" in msg.content[0].text.upper()


# ── Answer generation ─────────────────────────────────────────────────────────

ANSWER_SYSTEM = """You are the Switchyard policy assistant for Northwind Logistics.
Answer questions using ONLY the policy excerpts provided.
Your answer must:
- Be concise and accurate
- Quote specific dollar limits, tier names, or thresholds from the policy text
- If the answer requires knowing the employee's grade/destination/context that was not provided, say so
- Never fabricate rules not present in the provided excerpts

Return a JSON object matching this schema exactly:
{
  "answer": "<plain English answer>",
  "confidence": <0.0–1.0>,
  "citations": [
    {"chunk_id": "<id>", "policy_id": "<TEP-XXX>", "section": "<§N>", "text": "<verbatim excerpt>", "score": <0.0–1.0>}
  ]
}
"""


def _build_context(chunks: list[ChunkResult]) -> str:
    parts = []
    for c in chunks:
        parts.append(
            f"[{c.policy_id} {c.section}] {c.title}\n{c.text}"
        )
    return "\n\n---\n\n".join(parts)


def _generate_answer(question: str, chunks: list[ChunkResult]) -> QAAnswerSchema:
    context = _build_context(chunks)
    user_msg = f"Policy excerpts:\n\n{context}\n\nQuestion: {question}"

    msg = _anthropic.messages.create(
        model=settings.reasoning_model,
        max_tokens=1024,
        system=ANSWER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()

    # Extract JSON robustly
    import json
    start = raw.find("{")
    end = raw.rfind("}") + 1
    data = json.loads(raw[start:end])

    # Enrich citations with actual chunk data (LLM may truncate)
    chunk_map = {c.chunk_id: c for c in chunks}
    enriched_citations = []
    for cit in data.get("citations", []):
        c = chunk_map.get(cit.get("chunk_id", ""))
        enriched_citations.append(
            CitationSchema(
                chunk_id=cit.get("chunk_id", ""),
                policy_id=cit.get("policy_id", c.policy_id if c else ""),
                section=cit.get("section", c.section if c else ""),
                text=cit.get("text", ""),
                score=cit.get("score", c.rerank_score or c.rrf_score if c else 0.0),
            )
        )

    return QAAnswerSchema(
        answer=data["answer"],
        confidence=float(data.get("confidence", 0.5)),
        citations=enriched_citations,
    )


# ── Public API ────────────────────────────────────────────────────────────────


async def answer_question(
    question: str,
    user_id: str,
    db: AsyncSession,
) -> QASession:
    session_id = uuid.uuid4()

    # 1. Scope gate
    in_scope = _is_in_scope(question)
    if not in_scope:
        session = QASession(
            id=session_id,
            user_id=user_id,
            question=question,
            answer=None,
            status=QAStatus.out_of_scope.value,
            citations=[],
            confidence=None,
        )
        db.add(session)
        await db.commit()
        return session

    # 2. Hybrid retrieval
    chunks = await hybrid_search(question, db)

    # 3. Retrieval confidence check
    if not chunks or chunks[0].final_score < settings.min_retrieval_score:
        session = QASession(
            id=session_id,
            user_id=user_id,
            question=question,
            answer=None,
            status=QAStatus.out_of_scope.value,
            citations=[],
            confidence=None,
        )
        db.add(session)
        await db.commit()
        return session

    # 4. Generate answer
    result = _generate_answer(question, chunks)

    session = QASession(
        id=session_id,
        user_id=user_id,
        question=question,
        answer=result.answer,
        status=QAStatus.in_scope.value,
        citations=[c.model_dump() for c in result.citations],
        confidence=result.confidence,
    )
    db.add(session)
    await db.commit()
    return session
