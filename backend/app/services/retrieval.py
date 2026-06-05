"""
Hybrid retrieval over policy_chunks:
  1. Dense:  pgvector cosine similarity
  2. Sparse: Postgres tsvector full-text (ts_rank)
  3. Fusion: Reciprocal Rank Fusion (RRF, k=60)
  4. Rerank: Claude claude-haiku scores each candidate 0–1 for query relevance

Returns a ranked list of ChunkResult ready for citation + context injection.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .embeddings import embed_query

_anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

RRF_K = 60  # RRF constant


@dataclass
class ChunkResult:
    chunk_id: str
    policy_id: str
    section: str
    title: str
    text: str
    domain_tags: list[str]
    rrf_score: float
    rerank_score: float | None = None

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.rrf_score


async def hybrid_search(
    query: str,
    db: AsyncSession,
    top_k: int | None = None,
    domain_filter: list[str] | None = None,
) -> list[ChunkResult]:
    """
    Run hybrid retrieval and return reranked results.

    domain_filter: restrict to chunks whose domain_tags overlap this list.
    """
    top_k = top_k or settings.retrieval_top_k
    rerank_k = settings.rerank_top_k

    query_embedding = await embed_query(query)
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # ── Dense retrieval ───────────────────────────────────────────────────────
    dense_sql = text(
        """
        SELECT id::text, policy_id, section, title, text, domain_tags,
               1 - (embedding <=> :emb::vector) AS score
        FROM policy_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> :emb::vector
        LIMIT :k
        """
    )
    dense_rows = (await db.execute(dense_sql, {"emb": emb_str, "k": top_k * 2})).mappings().all()

    # ── Sparse retrieval ──────────────────────────────────────────────────────
    # Use plainto_tsquery for robustness with multi-word queries
    sparse_sql = text(
        """
        SELECT id::text, policy_id, section, title, text, domain_tags,
               ts_rank(ts_vector, plainto_tsquery('english', :q)) AS score
        FROM policy_chunks
        WHERE ts_vector @@ plainto_tsquery('english', :q)
        ORDER BY score DESC
        LIMIT :k
        """
    )
    sparse_rows = (await db.execute(sparse_sql, {"q": query, "k": top_k * 2})).mappings().all()

    # ── Build ranked lists ────────────────────────────────────────────────────
    dense_ids = [r["id"] for r in dense_rows]
    sparse_ids = [r["id"] for r in sparse_rows]

    # All unique chunks from both lists
    seen: dict[str, dict] = {}
    for r in dense_rows:
        seen[r["id"]] = dict(r)
    for r in sparse_rows:
        seen.setdefault(r["id"], dict(r))

    # ── RRF fusion ────────────────────────────────────────────────────────────
    rrf: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids, start=1):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    for rank, cid in enumerate(sparse_ids, start=1):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    # Domain filter
    if domain_filter:
        rrf = {
            cid: score
            for cid, score in rrf.items()
            if any(tag in (seen[cid].get("domain_tags") or []) for tag in domain_filter)
        }

    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

    candidates = [
        ChunkResult(
            chunk_id=cid,
            policy_id=seen[cid]["policy_id"],
            section=seen[cid]["section"],
            title=seen[cid]["title"],
            text=seen[cid]["text"],
            domain_tags=seen[cid].get("domain_tags") or [],
            rrf_score=score,
        )
        for cid, score in ranked
    ]

    if not candidates:
        return []

    # ── Cross-encoder rerank with Claude claude-haiku ─────────────────────────────
    reranked = await _rerank(query, candidates[:rerank_k])
    return reranked


async def _rerank(query: str, candidates: list[ChunkResult]) -> list[ChunkResult]:
    """Ask Claude claude-haiku to score each candidate's relevance to the query (0–1)."""
    if not candidates:
        return candidates

    candidates_text = "\n\n".join(
        f"[{i}] {c.policy_id} {c.section} — {c.title}\n{c.text[:400]}"
        for i, c in enumerate(candidates)
    )

    prompt = (
        f"Query: {query}\n\n"
        "Rate each candidate's relevance to the query on a scale of 0.0 to 1.0.\n"
        "Return ONLY a JSON array of numbers, one per candidate, in order.\n"
        "Example: [0.9, 0.3, 0.7]\n\n"
        f"Candidates:\n{candidates_text}"
    )

    try:
        msg = _anthropic.messages.create(
            model=settings.extraction_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Extract JSON array robustly
        start = raw.find("[")
        end = raw.rfind("]") + 1
        scores: list[float] = json.loads(raw[start:end])
    except Exception:
        # Rerank failed — fall back to RRF order
        return candidates

    for c, score in zip(candidates, scores):
        c.rerank_score = float(score)

    return sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)
