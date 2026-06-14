# CLAUDE.md

## Project
[RAG] — RAG system with clickable citations. Ingests PDF/DOCX/MD/HTML
documents, indexes them with hybrid (dense + BM25) search in Qdrant, and answers
questions via Claude with structured citations (`[n]` markers + verifiable quotes).
Evaluated with RAGAS. Portfolio project #2, companion to "Nexus" (Node/React SaaS).

## Stack
- Backend: Python 3.11, FastAPI, SQLAlchemy + Alembic, Pydantic Settings
- Vector DB: Qdrant (dense + sparse/BM25 hybrid, RRF fusion)
- App DB: PostgreSQL (documents, chunks, conversations) | Cache: Redis
- Embeddings: OpenAI `text-embedding-3-small`, behind `EmbeddingProvider`
- LLM: Claude via Anthropic API, behind `LLMProvider`, structured JSON output
  (`{"answer": "...[n]...", "citations": [{number, document_id, page, section, quote, chunk_id}]}`)
- Re-ranking: cross-encoder (`bge-reranker-v2-m3`)
- Frontend: React + Vite + TypeScript
- Eval: RAGAS | Observability: Langfuse + Prometheus/Grafana + structlog

## Conventions
- ALL code, comments, docstrings, commit messages, and docs in English.
- One branch per roadmap phase: `feature/phase-N-<short-name>`.
- A phase is "done" when: tests pass, `docker-compose up` works end-to-end,
  and the README "status" section is updated to reflect it.
- Commit incrementally at logical checkpoints within a phase — never one
  giant commit at the end.
- `EmbeddingProvider` and `LLMProvider` must stay swappable: no
  OpenAI/Anthropic-specific code outside their provider implementations.
- Every chunk must retain `document_id`, `page_number` (nullable),
  `section_path` (nullable), `char_start`, `char_end` — these are required
  for citations and the source viewer. Don't drop them in later phases.

## Commands
- `docker-compose -f infra/docker-compose.yml up` — run full stack locally
- `cd backend && pytest` — backend tests
- `cd backend && ruff check . && black --check .` — backend lint
- `cd frontend && npm run lint && npm run test` — frontend lint/tests
- `cd eval && python run_ragas.py` — run RAGAS evaluation (stack must be running)

## Roadmap
The phase-by-phase plan and ready-to-use prompts live in `ROADMAP.md`.

- **Current phase: 3** — update this line as each phase is completed and merged.
- Before starting a phase, read its full section in `ROADMAP.md`.
- Do not start a phase whose dependencies (earlier phases) aren't marked
  done in the README status section.
- At the end of a phase, update this file's "Current phase" line as part
  of the final commit of that phase's branch.