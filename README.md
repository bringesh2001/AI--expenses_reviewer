<h1 align="center">
  <br/>
  🧾 AI-Assisted Expense Pre-Review
  <br/>
</h1>

<p align="center">
  <b>Automated, policy-grounded expense compliance — before a human ever sees the receipt.</b>
  <br/>
  <sub>FastAPI · React · Claude · pgvector · Supabase · Railway · Vercel</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/TypeScript-5.5-3178C6?logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Supabase-Postgres+pgvector-3ECF8E?logo=supabase&logoColor=white" />
  <img src="https://img.shields.io/badge/Claude-Haiku%20%2F%20Sonnet-D97706" />
</p>

---

## What Is This?

LoanLens is a full-stack AI system that automatically reviews employee expense submissions against company travel & expense (T&E) policy — and gives a traceable verdict with cited policy text before a human reviewer ever opens the claim.

An employee uploads a receipt PDF, the system:
1. **Extracts** structured fields (vendor, amount, category, dates, cabin class, city, etc.) using a vision-capable LLM.
2. **Retrieves** the most relevant policy sections using hybrid dense + sparse search.
3. **Reasons** with a stronger LLM to produce a verdict and cited policy text.
4. **Gates** the verdict deterministically — no hallucinated citations, no low-confidence approvals.
5. **Applies cross-item rules** — duplicate detection, daily meal caps, approval thresholds.
6. **Stores** an immutable audit trail so every override and AI decision is traceable.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Vite + React SPA (Vercel)                                      │
│  Login · Dashboard · New Submission · Detail · Policy Q&A       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS + Supabase JWT
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI (Railway — persistent container)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Submissions │  │  Policy Q&A  │  │      Employees         │ │
│  │  router     │  │  router      │  │      router            │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘ │
│         │                │                                      │
│  ┌──────▼────────────────▼──────────────────────────────────┐  │
│  │  Pipeline Service                                        │  │
│  │  extract_receipt → compute_verdict → cross-item rules    │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Retrieval Service (hybrid pgvector + tsvector + RRF)    │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                           │ SQLAlchemy asyncpg
┌──────────────────────────▼──────────────────────────────────────┐
│  Supabase Postgres + pgvector                                   │
│  employees · submissions · line_items · policy_chunks           │
│  audit_logs · qa_sessions                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vite + React 18 + TypeScript + Tailwind CSS |
| **Auth** | Supabase email auth (JWT validated on backend) |
| **Backend** | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| **Database** | Supabase Postgres + pgvector extension |
| **Embeddings** | Voyage AI `voyage-3` (1024-dim, free tier 200M tokens) |
| **LLM (fast)** | `claude-haiku-4-5` — extraction, scope gating, reranking |
| **LLM (strong)** | `claude-sonnet-4-6` — verdict reasoning, Q&A answers |
| **LLM (vision)** | `claude-sonnet-4-6` — scanned / image PDFs |
| **Hosting (BE)** | Railway (long-running container, persistent DB connections) |
| **Hosting (FE)** | Vercel |

---

## Design Rationale

### 1. Fixed Pipeline over an Agent Loop

The core review flow is a deterministic sequence — extract → retrieve → reason → gate — rather than a free-running agent that decides its own next steps.

**Why:** Agent loops with tool calls are non-deterministic; a hallucinated tool invocation can silently produce a wrong verdict. Every decision in this pipeline is traceable: you can inspect the raw LLM output, the retrieved chunks, and which gate (if any) downgraded the verdict. This makes the system auditable by a human reviewer.

### 2. Clause-Level Chunking

Policy PDFs are chunked at the section-heading level (one `§N.N` heading → one chunk). The retrieval unit and the citation unit are identical.

**Why:** If you chunk at the paragraph level, a retrieved section might straddle the heading boundary and produce a citation like _"see paragraph 4 of section 3"_, which is hard for a reviewer to locate. With clause-level chunking, every citation is a clean section reference (e.g., _"TEP-001 §3.2"_) that a human can look up in 10 seconds.

### 3. Hybrid Retrieval (Dense + Sparse + RRF)

Policy retrieval combines:
- **Dense** — Voyage AI embeddings + pgvector cosine similarity (semantic understanding)
- **Sparse** — Postgres `tsvector` full-text search (exact keyword matches)
- **Fusion** — Reciprocal Rank Fusion (RRF) to merge both ranked lists

**Why:** T&E policies contain exact dollar amounts, tier names, and regulatory phrases ("Tier 2 city", "$250/night", "per-diem") that semantic search frequently misses when the embedding space conflates paraphrases. Full-text search catches these exactly; dense search handles category-level semantics. Neither alone is sufficient.

### 4. Deterministic Verdict Gate

After the LLM returns a verdict, four deterministic checks are applied before the result is written to the database:

| Gate | Condition | Action |
|------|-----------|--------|
| **Retrieval floor** | Best retrieval score < threshold | Downgrade to `needs_review` |
| **Faithfulness** | Cited text is not a substring of the source chunk | Reduce confidence |
| **Grounding** | `rejected` or `flagged` verdict with zero citations | Downgrade to `needs_review` |
| **Confidence floor** | `min(model_conf, retrieval_conf, citation_conf)` < threshold | Downgrade to `needs_review` |

**Why:** LLMs can hallucinate citations — inventing a policy rule that doesn't exist, or quoting a phrase that isn't in the actual policy text. The gate catches these cases before they reach a human reviewer. The confidence score seen in the UI is always the _post-gate_ value, never the raw model output.

### 5. Append-Only Audit Trail

Every AI verdict, human override, and status change creates a new row in `audit_logs`. Approved submissions become read-only; nothing is ever updated in place.

**Why:** Expense fraud investigations often hinge on the ability to reconstruct what decision was made, when, and by whom. An in-place update model destroys that history. The append-only model also makes it trivial to show a reviewer the full decision timeline for any submission.

### 6. Context Snapshot

Employee grade and department are frozen into the submission row at creation time (`snapshot_grade`, `snapshot_department`).

**Why:** Policy limits often depend on employee grade (e.g., Grade 5+ can fly business class on flights > 6 hours). If an employee is promoted after submitting a claim, re-evaluating the submission against their new grade would produce a misleading audit record. The snapshot makes the audit trail self-contained and temporally correct.

### 7. Two-Model Strategy

Receipt extraction uses `claude-haiku` (fast, cheap); verdict reasoning and Q&A use `claude-sonnet-4-6` (stronger reasoning).

**Why:** Extraction is a structured-output task with a predictable schema — Haiku handles it reliably at ~10× lower cost. Verdict reasoning requires nuanced policy interpretation where a stronger model materially reduces errors. Keeping models separate allows independent cost and accuracy tuning.

### 8. Policy Q&A as a Separate Surface

The Policy Q&A page (RAG chatbot) is completely decoupled from the submission pipeline — same retrieval service, different router and session model.

**Why:** Reviewers and employees often want to ask "what _is_ the hotel policy for San Francisco?" before submitting a claim. A dedicated Q&A surface with explicit in-scope / out-of-scope classification prevents the LLM from answering questions it has no grounding for (e.g., "can I expense my gym membership?").

---

## Verdict Taxonomy

| Verdict | Meaning |
|---------|---------|
| `compliant` | Policy permits the expense — no conditions unmet |
| `flagged` | Within policy but warrants attention (near limit, unusual pattern) |
| `needs_review` | Cannot determine compliance — missing info or low confidence |
| `rejected` | Policy clearly prohibits the expense as submitted |

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + lifespan
│   │   ├── config.py            # Pydantic settings (env-driven)
│   │   ├── database.py          # Async SQLAlchemy engine
│   │   ├── auth.py              # Supabase JWT verification
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── routers/             # FastAPI routers (submissions, qa, employees, health)
│   │   └── services/
│   │       ├── pipeline.py      # Orchestrator (Pass 1 + Pass 2)
│   │       ├── extraction.py    # Receipt field extraction (Haiku)
│   │       ├── verdict.py       # Per-item verdict + gate (Sonnet)
│   │       ├── retrieval.py     # Hybrid search (pgvector + tsvector + RRF)
│   │       ├── embeddings.py    # Voyage AI embedding helper
│   │       ├── qa.py            # Policy Q&A RAG pipeline
│   │       └── pdf_parser.py    # PDF → text / image extraction
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/               # LoginPage, DashboardPage, NewSubmissionPage,
│   │   │                        # SubmissionDetailPage, PolicyQAPage
│   │   ├── components/          # Shared UI components
│   │   ├── contexts/            # React context (auth, etc.)
│   │   ├── lib/                 # API client, Supabase client
│   │   └── types/               # TypeScript interfaces
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── ingest_policies.py       # Chunk + embed policy PDFs into Supabase
│   ├── build_dev_set.py         # Build eval dataset
│   └── run_eval.py              # Run accuracy / recall / faithfulness eval
├── policies/                    # Policy PDF source files (not committed)
├── eval/                        # Eval results (not committed)
└── .env.example                 # Environment variable template
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Supabase](https://supabase.com) project with the `pgvector` extension enabled
- An [Anthropic](https://console.anthropic.com) API key
- A [Voyage AI](https://dash.voyageai.com) API key (free tier: 200M tokens)

### 1. Clone & configure

```bash
git clone https://github.com/bringesh2001/AI--expenses_reviewer.git
cd AI--expenses_reviewer
cp .env.example .env          # fill in your keys (see table below)
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head           # run DB migrations
uvicorn app.main:app --reload  # http://localhost:8000
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local     # fill in Supabase URL + anon key + API URL
npm install
npm run dev                    # http://localhost:5173
```

### 4. Ingest policy documents

Place your T&E policy PDFs in `policies/` then:

```bash
cd backend
python ../scripts/ingest_policies.py --policies-dir ../policies
```

This chunks, embeds, and upserts every policy document into the `policy_chunks` table.

### 5. Run the evaluation suite

```bash
python scripts/build_dev_set.py
python scripts/run_eval.py --api-url http://localhost:8000
```

---

## Environment Variables

Copy `.env.example` to `.env` (backend) and fill in your values:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (backend only) |
| `SUPABASE_JWT_SECRET` | JWT secret for token verification |
| `DATABASE_URL` | `postgresql+asyncpg://...` connection string (use Transaction mode port 6543) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `VOYAGE_API_KEY` | Voyage AI API key |
| `CORS_ORIGINS` | Comma-separated allowed origins (e.g. `http://localhost:5173,https://your-app.vercel.app`) |
| `EXTRACTION_MODEL` | LLM for receipt extraction (default: `claude-haiku-4-5-20251001`) |
| `REASONING_MODEL` | LLM for verdict reasoning (default: `claude-sonnet-4-6`) |
| `EMBEDDING_MODEL` | Embedding model (default: `voyage-3`) |
| `EMBEDDING_DIM` | Embedding dimensions (default: `1024`) |

---

## Deployment

### Backend → Railway

1. Connect your GitHub repo to [Railway](https://railway.app).
2. Set all environment variables in the Railway project dashboard.
3. Railway detects the `Dockerfile` in `backend/` automatically.

### Frontend → Vercel

1. Import the repo into [Vercel](https://vercel.com).
2. Set the **Root Directory** to `frontend`.
3. Add environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`.
4. Deploy — Vercel auto-detects Vite.

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Coverage** | Fraction of items with a non-abstained verdict |
| **Accuracy@Coverage** | Accuracy only among covered items |
| **Dangerous-miss rate** | Expected-rejected items incorrectly marked compliant |
| **Retrieval Recall@k / MRR** | Gold citations appearing in top-k retrieved chunks |
| **Citation faithfulness** | Cited text is a substring of the source chunk |
| **Q&A scope accuracy** | Correct in-scope / out-of-scope classification rate |

---

## Cost & Scale Notes

The policy corpus (~100 pages, ~300 chunks) fits comfortably in Supabase's free pgvector tier with an `ivfflat` index (50 lists).

**LLM cost per submission (2 receipts):**
- ~$0.002 — Haiku extraction × 2
- ~$0.030 — Sonnet verdict × 2 + Q&A

Well under **$0.10 per submission** at current pricing.

At production scale (10k+ chunks): migrate to `hnsw` index and add a domain-filter pre-pass to reduce retrieval candidates before re-ranking.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you would like to change.

---

## License

MIT
