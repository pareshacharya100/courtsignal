Last Updated: 2026-10-19

# Live integrations — context

## Verified locally on 2026-10-19 (macOS 14.6, Python 3.13.5; CI covers 3.11/3.12 + PG16)

- Repo at origin/main 41805c6. `python -m pytest -q`: 31 passed (SQLite).
- Ingestion: Mata #54 and #55 created; SHA-256, page and chunk counts and quality checks identical to `docs/demo-ingestion.json`. Rerun: both `unchanged`, counts identical.
- NYSCEF #35: quarantined, HTTP 403. The response headers show `server: cloudflare` and `cf-mitigated: challenge` for both a project and a browser User-Agent. The earlier environment succeeded, so access depends on client/network. Do not bypass.
- Keyword evaluation: 4/4 federal queries at rank 1; 2 NYSCEF queries miss only because the document is absent.
- Local PostgreSQL is running but needs a password; PG tests were not run locally.

## Provider docs checked 2026-10-19

- Claude: `claude-sonnet-4-6` still served; `output_config.format` json_schema is the current structured-output shape; `anthropic-version: 2023-06-01`. Newer `claude-sonnet-5-5` is cheaper ($2/$10 vs $3/$15 per MTok) but has thinking on by default, which counts against `max_tokens` 3000. Not a drop-in switch; keep 4-6 unless deliberately changed and retested.
- Voyage (docs.voyageai.com/reference/embeddings-api): voyage-4-lite valid; input_type query/document; truncation bool; output_dimension 1024 default; max 1,000 inputs per request.
- Pinecone upsert (2025-10): `/vectors/upsert`, `Api-Key`, `X-Pinecone-Api-Version: 2025-10`, response `upsertedCount`, at most 1,000 vectors per request. Query contract not re-checked; the live run will confirm it.

## Decisions

- Keep raw httpx adapters (small, mockable, explicit retries and cost control) rather than switching to SDKs mid-project.
- Live runs are explicitly bounded; generative POSTs are never auto-retried.
