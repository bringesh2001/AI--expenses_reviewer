#!/usr/bin/env python3
"""
Ingest policy PDFs into policy_chunks table.

Usage:
    cd backend
    python ../scripts/ingest_policies.py --policies-dir ../policies

Pipeline per PDF:
1. Extract text with pypdf (fallback to Claude vision for scanned pages)
2. Split into clause-level chunks (one heading = one chunk)
3. Assign domain tags based on policy ID + content keywords
4. Generate embeddings (Voyage AI voyage-3, 1024-dim)
5. Build tsvector
6. Upsert into policy_chunks (idempotent on source_file + chunk_index)
"""
import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

# Add backend to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

import asyncpg
import voyageai
from pypdf import PdfReader

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-3")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

# Policy ID → domain tags mapping
POLICY_DOMAIN_MAP = {
    "TEP-001": ["general", "overview", "approval"],
    "TEP-002": ["meals", "per_diem"],
    "TEP-003": ["alcohol", "entertainment"],
    "TEP-004": ["lodging", "hotel", "tier"],
    "TEP-005": ["airfare", "air_travel", "cabin_class"],
    "TEP-006": ["ground_transport", "taxi", "rental_car", "mileage"],
    "TEP-007": ["receipts", "documentation", "requirements"],
    "TEP-008": ["per_diem", "rates", "tier"],
    "TEP-009": ["grade", "employee_grade", "approval_threshold"],
    "TEP-010": ["corporate_card", "payment"],
    "TEP-012": ["gifts", "entertainment", "client"],
}

# Known section heading patterns
SECTION_RE = re.compile(
    r"^(?P<section>§?\d+(?:\.\d+)*|Section\s+\d+(?:\.\d+)*)\s+(?P<title>.+)$",
    re.MULTILINE,
)

def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n".join(pages)


def detect_policy_id(text: str, filename: str) -> str | None:
    """Extract TEP-XXX from the text or filename."""
    m = re.search(r"TEP-\d{3}", text[:500])
    if m:
        return m.group(0)
    m = re.search(r"TEP-\d{3}", filename)
    return m.group(0) if m else None


def chunk_by_clauses(text: str, policy_id: str, source_file: str) -> list[dict]:
    """
    Split policy text at heading boundaries.
    Each chunk = one numbered section heading + its body text.
    """
    lines = text.splitlines()
    chunks = []
    current_section = "§0"
    current_title = "Preamble"
    current_body: list[str] = []
    chunk_index = 0

    def flush():
        nonlocal chunk_index
        body = "\n".join(current_body).strip()
        if not body:
            return
        chunk_text = f"{current_section} {current_title}\n{body}"
        tags = POLICY_DOMAIN_MAP.get(policy_id, [])
        chunks.append({
            "id": str(uuid.uuid4()),
            "policy_id": policy_id,
            "section": current_section,
            "title": current_title,
            "text": chunk_text,
            "domain_tags": json.dumps(tags),
            "source_file": source_file,
            "chunk_index": chunk_index,
        })
        chunk_index += 1

    for line in lines:
        m = SECTION_RE.match(line.strip())
        if m:
            flush()
            current_section = m.group("section").strip()
            current_title = m.group("title").strip()
            current_body = []
        else:
            current_body.append(line)

    flush()
    return chunks


import time

_voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed texts using Voyage AI, respecting the 3 RPM free-tier limit."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), 16):  # 16 texts per request to stay under 10K TPM
        batch = texts[i : i + 16]
        for attempt in range(5):
            try:
                result = _voyage_client.embed(batch, model=EMBEDDING_MODEL, input_type="document")
                all_embeddings.extend(result.embeddings)
                if i + 16 < len(texts):
                    time.sleep(21)  # 3 RPM → 20s between requests + 1s buffer
                break
            except voyageai.error.RateLimitError:
                wait = 25 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s (attempt {attempt+1}/5)")
                time.sleep(wait)
        else:
            raise RuntimeError("Voyage AI rate limit retries exhausted")
    return all_embeddings


async def upsert_chunks(chunks: list[dict], conn: asyncpg.Connection) -> None:
    for i in range(0, len(chunks), 100):
        batch = chunks[i : i + 100]
        texts = [c["text"] for c in batch]
        embeddings = embed_batch(texts)

        for chunk, emb in zip(batch, embeddings):
            await conn.execute(
                """
                INSERT INTO policy_chunks
                    (id, policy_id, section, title, text, domain_tags,
                     source_file, chunk_index, embedding)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9::vector)
                ON CONFLICT DO NOTHING
                """,
                chunk["id"],
                chunk["policy_id"],
                chunk["section"],
                chunk["title"],
                chunk["text"],
                chunk["domain_tags"],
                chunk["source_file"],
                chunk["chunk_index"],
                str(emb),
            )
            await conn.execute(
                """
                UPDATE policy_chunks
                SET ts_vector = to_tsvector('english', title || ' ' || text)
                WHERE id = $1 AND ts_vector IS NULL
                """,
                chunk["id"],
            )
        print(f"  Upserted batch {i // 100 + 1} ({len(batch)} chunks)")


async def ingest_file(pdf_path: Path, conn: asyncpg.Connection) -> None:
    print(f"\nIngesting {pdf_path.name}…")
    text = extract_text_from_pdf(pdf_path)
    policy_id = detect_policy_id(text, pdf_path.name) or "UNKNOWN"
    print(f"  Detected policy ID: {policy_id}")

    # Some PDFs contain multiple policies — split on each TEP-XXX header
    # and process each section separately
    tep_splits = list(re.finditer(r"(TEP-\d{3})", text))
    if len(tep_splits) <= 1:
        chunks = chunk_by_clauses(text, policy_id, pdf_path.name)
        print(f"  {len(chunks)} clause chunks")
        await upsert_chunks(chunks, conn)
    else:
        # Multi-policy PDF: split at each TEP boundary
        boundaries = [(m.start(), m.group(1)) for m in tep_splits]
        for idx, (start, pid) in enumerate(boundaries):
            end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(text)
            section_text = text[start:end]
            chunks = chunk_by_clauses(section_text, pid, pdf_path.name)
            print(f"  {pid}: {len(chunks)} chunks")
            await upsert_chunks(chunks, conn)


async def main(policies_dir: Path) -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    pdf_files = sorted(policies_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {policies_dir}")
        return

    for pdf in pdf_files:
        await ingest_file(pdf, conn)

    total = await conn.fetchval("SELECT count(*) FROM policy_chunks")
    print(f"\nDone. Total chunks in DB: {total}")
    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest policy PDFs into pgvector")
    parser.add_argument("--policies-dir", default="../policies", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.policies_dir))
