# CourtSignal — project instructions for Claude Code

Small, honest court-data demo: public PDFs → validated, page-preserving records → keyword/semantic search → optional Claude extraction and grounded answers. Built to be explained in a Data Engineer interview. Do not grow it into a platform.

## Commands

```bash
source .venv/bin/activate                     # Python 3.11+; local venv was created with 3.13
python -m pip install -c requirements-tested.txt -e '.[postgres,dev]'
python -m pytest -q                           # SQLite; set TEST_DATABASE_URL for an isolated PostgreSQL DB
courtsignal status                            # counts + which providers are configured (never prints keys)
courtsignal ingest --report data/ingestion.json
courtsignal search "fake opinions sanctions"
courtsignal evaluate --report data/evaluation.json
courtsignal serve                             # http://127.0.0.1:8000, API docs at /docs
courtsignal export-demo --output data/demo.html
```

Paid/external commands — run only when the user has authorized a bounded live run: `enrich`, `index`, `answer`, `search --mode semantic`, `evaluate --mode semantic`, `recap`.

## Module map (src/courtsignal)

models (contracts, stable IDs) → transport (bounded downloads, retries, host allowlist) → sources (RECAP archive reads) → parsing (pages, stamp checks, chunks, quote checks) → pipeline (orchestration, quarantine) → storage (transactional SQLite/PostgreSQL, `case_timeline` view) → providers (Claude, Voyage, Pinecone over raw httpx) → search (BM25, semantic + SQL hydration) → api (read-only FastAPI) / cli / snapshot (offline HTML). Design rationale: `docs/design.md`.

## Invariants — preserve these

- A document, its pages and chunks commit in one transaction; a failed refresh never replaces the current record.
- Raw PDFs are immutable and named by SHA-256. Pinned hashes in manifests reject changed sources.
- Chunk IDs include document ID, content hash, parser version, page and offsets. Chunks never cross pages.
- Replacing a document deletes its extractions. `save_extraction` rejects a stale content hash.
- Semantic hits are hydrated from current SQL chunks; unknown/stale vector IDs are dropped.
- Model output never becomes canonical case metadata. Quote checks prove presence, not entailment.
- Generative/embedding POSTs are not auto-retried (duplicate cost). Provider error bodies and auth headers are never surfaced.
- The API is read-only and binds to 127.0.0.1. Enrichment/indexing stay CLI-only.
- Keep the NYSCEF service-date vs clerk-stamp regression test (`test_nyscef_service_date_is_not_filing_date`).
- Missing services produce explicit errors; never substitute keyword results labeled as semantic.

## Honesty rules for docs, commits and chat

- Federal sample = Justia's published copies of SDNY opinions. Not PACER, not live RECAP.
- NYSCEF sample = one selected public document. Not discovery or bulk scraping.
- As of 2026-10-19, NYSCEF serves a Cloudflare bot challenge to non-browser clients (HTTP 403). Do not attempt to bypass it.
- Claude, Voyage, Pinecone and authenticated RECAP are mocked in tests until a recorded live run says otherwise (see `dev/active/live-integrations/`).
- Extraction defaults to the first 3 pages and records that scope. The 6-query evaluation is a smoke test, not a benchmark.
- No claims of production scale, full court coverage, AWS deployment or compliance.
- Report actual command output; if something was skipped or failed, say so.

## Working rules

- Read the relevant module and its tests before editing. Match the existing terse style.
- Bug fix → failing test first, then the fix. Run `python -m pytest -q` before saying something works.
- Verify current provider docs before changing API contracts or model names.
- Secrets live only in `.env` (gitignored). Never read, print, log or commit key values; check presence with `courtsignal status`.
- Do not purchase services, publish, push, or message anyone without the user's instruction.
- Task notes for multi-session work: `dev/active/<task>/` (use `/dev-docs`, `/dev-docs-update`).
