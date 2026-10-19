Last Updated: 2026-10-19

# Live integrations — plan

Goal: run each optional integration once, bounded, on the existing small corpus, and record actual results. No code rewrite.

Current state: adapters implemented and covered by `httpx.MockTransport` tests (`tests/test_services.py`, `tests/test_search_api.py`). Never run live. No keys configured locally (`courtsignal status`).

## Steps (smallest first)

1. Restore the full corpus. NYSCEF doc 35 is blocked by a Cloudflare challenge for non-browser clients; get the PDF by a manual browser download and ingest it under its pinned SHA-256 (needs a small local-file option; see tasks).
2. Claude extraction: set `ANTHROPIC_API_KEY` (a Console API key; Claude Code login does not provide it). Run `courtsignal enrich` on doc 54 with `--max-pages 3`. Bound: 1 request, about 3 pages in, `max_tokens` 3000.
3. Claude answer: `courtsignal answer "Why did the court impose sanctions?"` (keyword retrieval, 5 chunks). Bound: 1 request.
4. Voyage + Pinecone: create a serverless dense index, 1024 dims, cosine (free Starter tier if available; do not enable paid plans). Set the keys and host, use namespace `courtsignal-dev`. Run `courtsignal index` (94 chunks → 3 Voyage requests, 2 Pinecone upserts), then 1 semantic search and `evaluate --mode semantic` (6 query embeddings).
5. Record results in `docs/` (e.g. `docs/live-validation.json`) and update README execution status with what actually ran.

## Risks

- A model may return a quote that fails the presence check. That is the guard working; record it, don't loosen it.
- Pinecone query is eventually consistent; an immediate query after upsert can return fewer matches.
- RECAP needs a CourtListener token and a docket with archived documents; optional, last.

## Acceptance

Each step has a saved JSON output with date, model, counts and any failure, and no secrets in files or logs.
