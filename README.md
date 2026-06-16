# RAG — RAG with clickable citations

A Retrieval-Augmented Generation system that ingests documents
(PDF / DOCX / Markdown / HTML), indexes them with **hybrid search** (dense
embeddings + BM25) in Qdrant, and answers questions with **Claude** using
structured, verifiable citations — every answer carries `[n]` markers backed by
exact quotes and a clickable source location (document, page, section).

> Portfolio project #2 — companion to "Nexus" (Node/React SaaS).

## Overview

- **Backend** — Python 3.11 + FastAPI, SQLAlchemy + Alembic, Pydantic Settings.
- **Vector DB** — Qdrant (dense + sparse/BM25 hybrid retrieval, RRF fusion).
- **App DB** — PostgreSQL (documents, chunks, conversations).
- **Cache** — Redis.
- **Embeddings** — OpenAI `text-embedding-3-small`, behind a swappable
  `EmbeddingProvider`.
- **LLM** — Claude (Anthropic API), behind a swappable `LLMProvider`, structured
  JSON output with citations.
- **Re-ranking** — cross-encoder (`bge-reranker-v2-m3`).
- **Frontend** — React + Vite + TypeScript.
- **Eval / Observability** — RAGAS, Langfuse, Prometheus/Grafana, structlog.

## Architecture

```mermaid
flowchart LR
    subgraph Ingestion["Ingestion pipeline"]
        U[Documents<br/>PDF / DOCX / MD / HTML] --> P[Parse & chunk<br/>page / section metadata]
        P --> E[Embed<br/>EmbeddingProvider]
    end

    subgraph Stores["Stores"]
        VS[(Qdrant<br/>dense + BM25)]
        PG[(PostgreSQL<br/>documents / chunks / conversations)]
        RD[(Redis<br/>cache)]
    end

    E --> VS
    P --> PG

    subgraph Retrieval["Retrieval"]
        Q[User question] --> H[Hybrid search<br/>RRF fusion]
        H --> RR[Cross-encoder<br/>re-ranking]
    end

    VS --> H
    PG --> H
    RD -.cache.-> H

    subgraph Generation["Generation"]
        RR --> LLM[Claude<br/>LLMProvider]
        LLM --> ANS["Answer + citations<br/>#91;n#93; markers + quotes"]
    end

    subgraph Frontend["Frontend (React + Vite)"]
        ANS --> UI[Chat UI]
        UI --> SRC[Clickable source viewer]
    end

    API{{FastAPI}} --- Retrieval
    API --- Generation
    UI <--> API
```

The data flow is: **ingestion pipeline → vector store → retrieval → generation →
frontend**.

## Repository layout

```
rag/
├── backend/            # FastAPI app (api, core, services, models, db, schemas)
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/           # Vite + React + TypeScript
│   ├── src/
│   ├── nginx.conf      # serves the SPA and proxies /health + /api to backend
│   └── Dockerfile
├── infra/
│   └── docker-compose.yml
├── .env.example        # root env for docker-compose
└── .github/workflows/  # CI: lint + tests (backend & frontend)
```

## How to run locally

### Option A — full stack with Docker (recommended)

Requires Docker + Docker Compose.

```bash
# from the repository root
docker-compose -f infra/docker-compose.yml up --build
```

This starts PostgreSQL, Qdrant, Redis, the backend, and the frontend. Defaults
are baked into the compose file, so no `.env` is required. To customise
credentials or ports, copy `.env.example` to `.env` first:

```bash
cp .env.example .env
```

Once it's up:

- Frontend: <http://localhost:5173>
- Backend health: <http://localhost:8000/health>
- API docs (Swagger): <http://localhost:8000/docs>

`GET /health` returns `200` with `{"status": "ok", ...}` when the app and all
three backing services (PostgreSQL, Qdrant, Redis) are reachable; it returns
`503` with `{"status": "degraded", ...}` if any dependency is down.

### Option B — run services separately (development)

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # point hosts at localhost
# start postgres/qdrant/redis however you like (e.g. the compose file above)
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /health + /api to :8000
```

## Development commands

| Task                 | Command                                                    |
| -------------------- | ---------------------------------------------------------- |
| Backend tests        | `cd backend && pytest`                                     |
| Backend lint         | `cd backend && ruff check . && black --check .`            |
| Frontend lint        | `cd frontend && npm run lint`                              |
| Frontend tests       | `cd frontend && npm run test`                              |
| Frontend type-check  | `cd frontend && npm run build`                             |
| Full stack (Docker)  | `docker-compose -f infra/docker-compose.yml up --build`    |
| RAGAS evaluation     | `make eval` (stack must be running — see [Evaluation](#evaluation)) |

## Status

Phase-by-phase progress (see `ROADMAP.md` for the full plan):

- ✅ **Phase 0 — Project scaffold**: monorepo structure, FastAPI `/health` with
  Postgres/Qdrant/Redis connectivity checks, React + Vite frontend showing the
  health status, Docker Compose for the full stack, and CI (lint + tests).
  Verified end-to-end via `docker-compose -f infra/docker-compose.yml up --build`:
  `GET /health` returns `200` with `{"status": "ok"}` and `postgres`, `qdrant`,
  and `redis` all reporting `"ok"` (confirmed both on the backend at `:8000` and
  through the frontend's nginx proxy at `:5173`).
- ✅ **Phase 1 — Ingestion & chunking with metadata**: `Document`/`Chunk`
  models with Alembic migrations; parsers for PDF (`pypdf`), DOCX
  (`python-docx`), Markdown (`markdown-it-py`) and HTML (`BeautifulSoup4`) that
  preserve page numbers and heading breadcrumbs (`section_path`); token-based
  chunking (`tiktoken`, ~400 tokens / ~50 overlap) that keeps
  `page_number`/`section_path` and `char_start`/`char_end` offsets; and the
  `POST /documents` (background processing), `GET /documents`,
  `GET /documents/{id}`, `GET /documents/{id}/chunks` endpoints. Verified
  end-to-end via docker-compose (upload → parse → chunk → `status=indexed`) and
  10 unit tests covering parser metadata and chunk overlap/offsets.
- ✅ **Phase 2 — Embeddings + Qdrant indexing**: swappable `EmbeddingProvider`
  with an OpenAI implementation (`text-embedding-3-small`, 1536-dim, batching +
  retry/backoff); a hybrid Qdrant collection (dense cosine vector `dense` +
  sparse BM25 vector `sparse` with the IDF modifier, via FastEmbed); an
  idempotent indexing job that embeds a document's chunks (dense + sparse) and
  upserts them into Qdrant keyed by chunk id, stamping `chunks.embedded_at`
  (migration `0002`, also exposed on `GET /documents/{id}/chunks`) so they are
  not reprocessed; automatic indexing after ingestion plus a manual
  `POST /documents/{id}/index` endpoint. Covered by Qdrant-backed integration
  tests (idempotency / no-duplicate / similarity search) that skip when Qdrant
  or `OPENAI_API_KEY` is unavailable. Verified end-to-end via docker-compose
  with **real OpenAI embeddings** (migration `0002` auto-applied on startup;
  uploading `sample.md` → `status=indexed`, every chunk's `embedded_at`
  populated, and the `chunks` collection holding a matching number of points
  with `dense` + `sparse` vectors).
- ✅ **Phase 3 — Hybrid retrieval + re-ranking**: a `RetrievalService` that
  embeds the query (dense + BM25 sparse), runs a hybrid Qdrant search — a
  `dense` and a `sparse` `Prefetch` fused server-side with `FusionQuery`/RRF —
  then re-ranks the fused candidates with a cross-encoder and returns the
  top-`k`. Supports a `document_ids` payload filter, and each result carries
  `chunk_id`, `document_id`, `document_filename`, `page_number`, `section_path`,
  `content`, the RRF `score` and the `rerank_score`. Exposed via
  `POST /retrieve` (internal/debug). The Qdrant server image was aligned to the
  client (`v1.18.0`) so the Query API runs without the version-skew warning.
  Covered by Qdrant-backed tests — including one that shows pure-dense search
  missing an exact-keyword chunk that hybrid (RRF) recovers — plus a
  cross-encoder re-ranking test; they skip when Qdrant is unavailable. The
  reranker default and the rationale are documented under
  [Re-ranking](#re-ranking). Verified end-to-end via docker-compose on the new
  Qdrant `v1.18.0` image (fresh volume): uploading `sample.md` → `status=indexed`,
  then `POST /retrieve` with `{"query": "What does section 2.1 discuss?",
  "top_k": 3}` returned the `Chapter 2 > Section 2.1` chunk on top — with the
  highest `rerank_score` (clearly separated from the rest) and the RRF `score`,
  `document_filename`, `section_path` and `content` all populated correctly.
- ✅ **Phase 4 — Cited generation**: a swappable `LLMProvider` (Anthropic
  implementation) with two stages — `generate_answer` streams a plain-text answer
  grounded only in the numbered context chunks, inserting `[n]` markers where each
  source is used; `extract_citations` runs a separate, forced tool-use call that
  returns `{number, chunk_id, quote}` objects, dropping any unknown `chunk_id` and
  repairing each `quote` to the exact verbatim span in its chunk (the model
  normalizes the chunk's hard line-wrap newlines into spaces when quoting, so the
  span is snapped back for offset-accurate highlighting). A `ChatService` ties
  retrieval and generation together: it creates a `Conversation` and persists the
  user/assistant `Message`s (migration `0003`), short-circuits to a fixed
  "I don't have enough information…" answer **without calling the LLM** when
  retrieval is empty (zero token cost), and enriches each citation with
  `document_id`/`document_name`/`page`/`section`. Exposed via `POST /chat`
  (Server-Sent Events: a stream of `delta` events then a terminal `citations`
  event; `503` without `ANTHROPIC_API_KEY`). Models are configurable
  (`generation_model` default `claude-sonnet-4-6`, `citation_extraction_model`
  default `claude-haiku-4-5-20251001`). Covered by unit tests over in-memory
  SQLite with a fake provider (streaming/persistence, conversation reuse, the
  no-chunks short-circuit, the verbatim-quote repair) plus real-Anthropic
  integration tests that skip without a key. Verified end-to-end via
  docker-compose with **real Claude**: uploading `sample.md` → `status=indexed`,
  then `POST /chat` (via `curl -N`) for "What does section 2.1 discuss?" streamed
  the answer incrementally (multiple `delta` events over ~2 s) and returned
  citations whose `quote`s are exact, newline-accurate substrings of the cited
  chunk; an unrelated question returned the "I don't have enough information…"
  refusal with no citations.
- ✅ **Phase 5 — Frontend: chat + clickable citations**: a React + Vite + TS SPA
  (React Router) with two pages. **Chat** streams the answer live by reading the
  `POST /chat` SSE body (`fetch` + `ReadableStream`, accumulating `delta` text);
  once the terminal `citations` event arrives, `CitedAnswer` parses the `[n]`
  markers and renders each as a clickable badge. Clicking a badge opens the
  **`SourceViewer`** side panel, which fetches the full chunk via the new
  `GET /chunks/{id}` and highlights the cited `quote` inside the passage. The
  `conversation_id` from the first turn is threaded into subsequent calls for a
  continuous conversation. **Documents** supports drag-and-drop / file-picker
  upload (`POST /documents`), a table of documents with status, chunk count and
  upload time (light 3 s polling so `pending → processing → indexed/failed`
  updates live), and deletion via the new `DELETE /documents/{id}` (cascades to
  chunks, best-effort cleanup of the Qdrant points and the stored source file).
  Backend tests cover `GET /chunks/{id}` and the delete cascade over in-memory
  SQLite (ASGI transport, Qdrant/filesystem stubbed); each new frontend component
  has a Vitest test (React Testing Library + stubbed `fetch`, including a
  `ReadableStream` SSE double). `npm run test`, `npm run lint` and `npm run build`
  all pass. The browser calls the backend under an `/api` prefix that the Vite
  dev proxy and the nginx (Docker) config strip before forwarding, so the REST
  resources never shadow the client-side routes (e.g. the `/documents` SPA route
  vs the `/documents` resource); nginx disables response buffering on `/api` so
  the `/chat` stream is delivered incrementally. Verified end-to-end via
  `docker-compose up --wait` (all services healthy, `alembic current` at `0003`):
  through the nginx origin on `:5173`, navigating to `/documents` serves the SPA
  while `/api/documents` returns JSON; uploading `sample.md` polled
  `pending → processing → indexed` (3 chunks); asking "What does section 2.1
  discuss?" streamed the answer over 6 `delta` events then returned `[n]`
  citations whose `quote`s are verbatim substrings of the cited chunk fetched via
  `GET /api/chunks/{id}`; a follow-up question reused the same `conversation_id`;
  and deleting the document returned `204`, emptied the list, and cascaded the
  chunk to `404`.
- 🧪 **Phase 6 — Evaluation (RAGAS)**: an evaluation harness under `eval/` that
  scores the live pipeline over HTTP (no backend imports). `eval/dataset.json`
  holds 20 questions grounded in the test fixtures (`sample.md`/`.pdf`/`.docx`/
  `.html`), 4 of them intentionally unanswerable to probe faithfulness and the
  "I don't know" refusal. `eval/run_ragas.py` streams `POST /chat` for each
  question, builds `contexts` from the cited chunks (`GET /chunks/{id}`), and
  scores `faithfulness`, `answer_relevancy`, `context_precision` and
  `context_recall` via RAGAS (OpenAI judge), plus a custom `citation_accuracy`
  (each citation's `quote` must be a verbatim substring of its referenced
  chunk). It writes `eval/results/report.{json,md}` and prints an aggregate
  summary. Run it with `make eval` (stack up) or trigger the manual
  `RAGAS evaluation` GitHub Action (`.github/workflows/eval.yml`), which boots
  the compose stack, indexes the fixtures, and uploads the report as an
  artifact. See [Evaluation](#evaluation). _Harness verified by unit-checking its
  parsing/scoring/reporting helpers; the full RAGAS run requires a live stack
  plus `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, so it has not been executed in this
  environment yet._
- ⬜ Later phases: observability/cost, and deploy/CI-CD.

### API endpoints

| Method & path                    | Description                                            |
| -------------------------------- | ------------------------------------------------------ |
| `GET /health`                    | App + dependency (Postgres/Qdrant/Redis) status        |
| `POST /documents`                | Upload a PDF/DOCX/MD/HTML file; ingests in background   |
| `GET /documents`                 | List uploaded documents with status                    |
| `GET /documents/{id}`            | Document details + chunk count                          |
| `DELETE /documents/{id}`         | Delete a document (cascades to chunks; clears vectors + file) |
| `GET /documents/{id}/chunks`     | List a document's chunks with citation metadata         |
| `POST /documents/{id}/index`     | Re-embed and (re-)index a document into Qdrant (hybrid)  |
| `GET /chunks/{id}`               | Fetch a single chunk by id (source viewer)             |
| `POST /retrieve`                 | Hybrid search + re-ranking (internal/debug); scored chunks |
| `POST /chat`                     | Cited answer generation over SSE (`delta` stream + `citations`) |

### Re-ranking

Retrieval is two-stage: a fast hybrid first stage (dense + BM25, fused with RRF
in Qdrant) over-fetches ~20 candidates, then a **cross-encoder** re-scores each
`(query, chunk)` pair jointly and the top-`k` are returned.

The default cross-encoder is **`cross-encoder/ms-marco-MiniLM-L-6-v2`** (set via
`RERANKER_MODEL`). It was chosen deliberately for this CPU-only Docker setup: at
~80 MB it builds and downloads quickly and re-ranks ~20 candidates in
milliseconds on CPU. Heavier rerankers such as `BAAI/bge-reranker-v2-m3` are
more accurate but several times larger and noticeably slower to load and run
without a GPU — overkill for a local/demo deployment. Swapping is trivial:
`RERANKER_MODEL` accepts any `sentence-transformers` cross-encoder, so a
GPU-backed deployment can opt into a stronger model with no code change.

> Torch is installed from PyTorch's **CPU-only wheel index**
> (`--extra-index-url https://download.pytorch.org/whl/cpu` in
> `requirements.txt`) to avoid pulling multi-GB CUDA builds that this image
> would never use.

## Evaluation

The RAG quality is measured with [RAGAS](https://docs.ragas.io) plus a custom
citation metric. The harness lives in [`eval/`](eval/) and talks to a **running
stack over HTTP only** (it never imports backend code), so it runs from its own
virtualenv against any deployment.

For each question in [`eval/dataset.json`](eval/dataset.json) it streams
`POST /chat`, reads the answer and the structured `citations`, and rebuilds the
`contexts` from the **cited** chunks by fetching each `GET /chunks/{id}`. The
dataset holds **20 questions** grounded in the test fixtures
(`backend/tests/fixtures/sample.{md,pdf,docx,html}`), including **4 questions
that the documents intentionally do not answer** — these probe whether the
system refuses ("I don't have enough information…") instead of hallucinating.

### Metrics

| Metric | What it measures here |
| --- | --- |
| **faithfulness** | Is every claim in the answer supported by the retrieved (cited) context? Low scores flag hallucination. The unanswerable questions should produce a refusal with no unsupported claims. |
| **answer_relevancy** | Does the answer actually address the question (vs. being off-topic or padded)? Computed from the generated answer against the question via embeddings. |
| **context_precision** | Of the context we surfaced (the cited chunks), how much is actually relevant to the ground-truth answer? Penalises citing noise. |
| **context_recall** | Does the cited context cover everything the ground-truth answer needs? Low scores point at retrieval misses. (Use `expected_chunk_ids` in the dataset for manual recall analysis.) |
| **citation_accuracy** (custom) | The share of returned citations whose `quote` is a verbatim (whitespace-normalised) substring of the referenced chunk's `content`. This is the project's headline guarantee — every `[n]` marker must be backed by a real, locatable quote — checked directly rather than via an LLM judge. Reported both as a mean per question and pooled over all citations. |

> RAGAS scores answers with an **LLM judge** (OpenAI by default) and uses
> embeddings for `answer_relevancy`, so `OPENAI_API_KEY` is required.
> `citation_accuracy` is pure string matching and needs no LLM.

The run writes [`eval/results/report.json`](eval/results/) (per-question +
aggregate scores) and `report.md` (a readable summary that highlights the
**three worst questions by faithfulness** for analysis), and prints the
aggregate scores to stdout.

### Running it locally

The stack must be up and the fixtures indexed. API keys are read from the
repo-root `.env` automatically (`OPENAI_API_KEY` for the RAGAS judge,
`ANTHROPIC_API_KEY` for the backend's generation).

```bash
# 1. Start the full stack
docker-compose -f infra/docker-compose.yml up --build -d

# 2. Install the eval dependencies (one-off, into eval/.venv)
make eval-install

# 3. Run the evaluation (verifies /health, indexes the fixtures, scores them)
make eval
```

`make eval` checks `GET /health`, (idempotently) uploads + indexes the four
fixtures, then runs the evaluation. Without `make` (e.g. plain Windows Git Bash)
use the equivalent shell script:

```bash
bash eval/run.sh
```

Point the harness at a non-default backend with `RAG_API_BASE_URL`
(default `http://localhost:8000`), e.g. `make eval BASE_URL=http://host:8000`.

### In CI

[`.github/workflows/eval.yml`](.github/workflows/eval.yml) runs the evaluation
on demand (`workflow_dispatch` — it is **not** part of the per-push CI because it
spends OpenAI/Anthropic credits). Trigger it from the Actions tab; it boots the
docker-compose stack, indexes the fixtures, runs `eval/run_ragas.py`, and
publishes `eval/results/report.md` (and `report.json`) as a workflow artifact.
It needs the repository secrets `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`.
