# CourtSignal

Court records into structured, searchable evidence—with a page behind every result.

A small data-engineering project covering acquisition, normalization, validation, storage, grounded extraction, and retrieval. The included corpus contains **2 cases, 3 documents, 53 pages, and 94 page-preserving passages**. It includes federal opinions in *Mata v. Avianca* and a filing downloaded directly from NYSCEF.

## Try it

**Without setup:** download [docs/demo.html](docs/demo.html) and open it in a browser. This standalone snapshot contains the actual ingested records, keyword search, case timelines, source links, and a document inspector. It makes no AI API calls. GitHub displays the HTML source; download the raw file to use it.

**Run the pipeline and API locally** (Python 3.11+):

```bash
git clone https://github.com/pareshacharya100/courtsignal.git
cd courtsignal
python -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-tested.txt -e '.[dev]'
cp .env.example .env
courtsignal ingest --report data/ingestion.json
courtsignal search "fake opinions sanctions"
courtsignal serve
```

Open `http://127.0.0.1:8000`. API documentation is at `/docs`. The default SQLite store needs no services or API keys. Windows users can activate with `.venv\Scripts\activate`.

## What is implemented

| Stage | Behavior |
|---|---|
| Acquisition | Public PDF manifests; a bounded, authenticated CourtListener RECAP adapter for existing archived documents |
| Normalization | Separate case/document contracts; court-scoped case identity; attachment identity; normalized text and page-local character offsets |
| Validation | PDF sniffing, SHA-256 pins, court-stamp checks for case/document/date, text coverage, OCR flags, quarantine events |
| Storage | Immutable raw PDFs; transactional PostgreSQL or SQLite tables; deterministic chunk IDs; idempotent reruns; extraction invalidation after changes |
| Extraction | Opt-in Claude structured outputs, Pydantic validation, page/quote checks, recorded model and partial-document scope |
| Search | Local BM25 baseline; optional Voyage document/query embeddings and Pinecone retrieval; SQL hydration rejects stale vector IDs |
| RAG | Opt-in Claude answers restricted to retrieved chunk IDs and supporting quotes; abstention on empty retrieval |
| Access | FastAPI explorer, read-only API, CLI, standalone offline snapshot, six-query evaluation set |

## Source provenance

| Case | Documents | Origin and actual acquisition |
|---|---|---|
| *Mata v. Avianca, Inc.*, SDNY `1:22-cv-01461` | #54 sanctions opinion (43 pages); #55 dismissal opinion (7 pages), June 22, 2023 | Federal court opinions, downloaded from Justia's published copies. **Not a direct PACER or live RECAP run.** |
| *Garcia v. The Lillian Goldman Family, LLC et al.*, Queens Supreme Court `701695/2024` | #35 Request for Judicial Intervention (3 pages), September 23, 2024 | Public NYSCEF document downloaded from the official court site |

Exact source URLs and SHA-256 hashes are in [examples/demo.json](examples/demo.json). The corpus is deliberately small. The NYSCEF adapter consumes selected public document URLs; it does not discover all cases or automate guest search. Source availability can change; the pinned hash intentionally rejects a changed PDF.

*Mata* is a useful sample because the sanctions opinion addresses fabricated AI-generated case citations. It makes provenance and evidence checking concrete.

## Enable Claude, Voyage and Pinecone

Add keys to your local `.env`; it is ignored by git. Never put keys in source code. Commands below explicitly invoke external services and may incur usage charges.

1. Set `ANTHROPIC_API_KEY`. The model is configurable through `ANTHROPIC_MODEL`.
2. Set `VOYAGE_API_KEY`. The default is `voyage-4-lite`, 1024 dimensions.
3. Create a Pinecone dense index with **1024 dimensions and cosine similarity**. Set `PINECONE_API_KEY` and its HTTPS `PINECONE_INDEX_HOST`. Use a separate namespace when changing embedding models or dimensions.

```bash
# Extract the first three pages of the sanctions opinion.
courtsignal enrich --document-id aa0364d13468648510f665d798a2d3d845ea0d8c2726a5d86267b97dd8e22d67 --max-pages 3

# Embed with input_type=document, cache embeddings, then upsert to Pinecone.
courtsignal index

# Embed the query with input_type=query and hydrate results from canonical SQL.
courtsignal search "What happened when counsel submitted invented cases?" --mode semantic
courtsignal answer "Why did the court impose sanctions?" --mode semantic
courtsignal evaluate --mode semantic --report data/semantic-evaluation.json
```

The UI's semantic option returns a clear setup error when services are missing. It never substitutes keyword results while labeling them semantic. Claude quotes are checked against supplied pages/passages; **quote presence does not prove that a claim is entailed or legally correct**. Human review remains necessary. `--max-pages` is a hard scope limit, not a claim of full-document extraction.

## Acquire existing RECAP documents

Set `COURTLISTENER_TOKEN` locally, then supply a known CourtListener docket ID:

```bash
courtsignal recap --docket-id YOUR_DOCKET_ID --limit 5 --max-pages 3 --output data/recap-manifest.json
courtsignal ingest --manifest data/recap-manifest.json
```

The adapter follows bounded docket-entry pagination, skips unavailable documents, includes attachments, and validates pagination URLs before sending the token. It uses only archive reads, never PACER purchase endpoints. API 429/502/503/504 responses receive bounded retries. PDF download failures are quarantined for explicit reruns.

## PostgreSQL

```bash
python -m pip install -c requirements-tested.txt -e '.[postgres,dev]'
docker compose up -d --wait
# In .env, set DATABASE_URL to:
# postgresql://courtsignal:courtsignal@localhost:5432/courtsignal
courtsignal ingest
courtsignal serve
```

The Compose password is for this local development database, bound to loopback. Both stores use the same contracts and transactions. `case_timeline` is a curated SQL view over canonical records, keeping source metadata separate from model-derived facts.

## Validation and recorded results

```bash
python -m pytest -q
courtsignal ingest --report data/rerun.json
courtsignal evaluate --report data/evaluation.json
courtsignal export-demo --output data/demo.html
```

Recorded evidence is in [docs/demo-ingestion.json](docs/demo-ingestion.json), [docs/demo-rerun.json](docs/demo-rerun.json), and [docs/demo-evaluation.json](docs/demo-evaluation.json). All three sample records passed case-number, document-number, and filing-date checks; all 53 pages yielded text. Rerunning left canonical record counts unchanged. The six hand-authored keyword queries retrieved their expected document at rank 1. This is a small demonstration set, not a general retrieval-quality claim.

Tests cover transactional rollback, changed-document invalidation, idempotency, a NYSCEF service-date/filing-date collision, scanned PDFs, checksum failures, fabricated extraction evidence, provider response handling, embedding validation/cache identity, stale vector IDs, source filters, API contracts, and snapshot escaping. CI runs the suite on SQLite and PostgreSQL 16. External service contracts use HTTP mocks.

**Execution status:** the public PDF downloads, SQLite ingestion, keyword retrieval, API tests, and offline export have run. Claude, Voyage, Pinecone, and authenticated RECAP have not run live because their keys are not configured. Their adapters are implemented and tested with mocked responses. PostgreSQL integration is included in CI; see the actual Actions result rather than assuming it passed.

## Design and limits

See [docs/design.md](docs/design.md) for the data model, failure boundaries, and scaling tradeoffs. This is a single-writer research prototype. It does not claim full PACER/NYSCEF coverage, production throughput, automatic legal verification, SOC 2 compliance, or production-ready hosting. PDFs with no usable text require a separate OCR step; image-only pages in mixed PDFs are flagged and excluded from indexing.

## API references

- [CourtListener PACER data APIs](https://wiki.free.law/c/courtlistener/help/api/rest/v4/pacer-data) and [file download fields](https://wiki.free.law/c/courtlistener/help/api/rest/v4/field-help)
- [Claude structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Voyage embeddings](https://docs.voyageai.com/reference/embeddings-api)
- [Pinecone upsert](https://docs.pinecone.io/reference/api/2025-10/data-plane/upsert) and [query](https://docs.pinecone.io/reference/api/2025-10/data-plane/query)
