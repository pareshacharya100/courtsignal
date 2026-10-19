# Design notes

## Ownership and boundaries

Acquisition produces validated `DocumentSpec` objects. Parsing preserves page boundaries. The store owns canonical records and commits each document together with its pages/chunks. Provider adapters know their external HTTP contracts. Search owns retrieval and SQL hydration. FastAPI only reads; enrichment and indexing require explicit CLI commands.

```
src/courtsignal/
  models.py       canonical contracts and stable identity
  sources.py      authenticated RECAP archive reads
  transport.py    bounded public downloads and HTTP retries
  parsing.py      PDF text, stamp checks, page-preserving chunks
  storage.py      transactional SQLite/PostgreSQL persistence
  pipeline.py     acquisition-to-storage orchestration
  providers.py    Claude, Voyage, Pinecone adapters
  search.py       BM25 and semantic retrieval
  api.py          read-only HTTP interface
  cli.py          explicit pipeline and provider operations
  snapshot.py    self-contained offline corpus export
```

## Canonical model

- `cases`: source system + court + docket/index number determine identity. Case names can change.
- `documents`: case + document number + attachment determine identity. Source URL, actual acquisition method, hash, parser version, retrieval time and validation result travel with the record.
- `pages`: normalized text at a PDF page number.
- `chunks`: deterministic content-versioned IDs and character offsets into normalized page text. They never cross pages. Offsets are not PDF glyph coordinates.
- `extractions`: separate model-derived facts, evidence quotes, model name, content hash and exact page scope. Replacing a document invalidates old extractions.
- `ingestion_events`: append-only created/updated/unchanged/quarantined outcomes. Failed refreshes leave the current canonical record intact.
- `case_timeline`: curated SQL view for downstream consumers. Unknown metadata remains unknown; it is not inferred to fill a column.

Raw PDFs live under their SHA-256 hashes. A failed refreshed document cannot overwrite the cached file for the current canonical version. Raw PDFs, runtime databases, API keys and embedding caches are ignored by git. The offline HTML deliberately embeds the selected public corpus for a reproducible demonstration; do not export private corpora to a public repository.

## Evidence and extraction

The NYSCEF sample exposed a real parsing ambiguity: a form's service-date field precedes the clerk stamp. The validator specifically matches the county-clerk filing stamp. Tests preserve this example.

Header validation recognizes common federal ECF and NYSCEF stamp patterns. An absent stamp is reported as unverified, while a detected mismatch is rejected. A successful stamp check does not authenticate the document or establish full metadata correctness. Scanned PDFs are not sent to an LLM as if text extraction had succeeded.

Claude receives only selected pages or retrieved passages and is told to treat them as untrusted evidence. JSON-schema decoding constrains shape; local Pydantic validation enforces limits unsupported by the provider's schema subset. Every saved fact must reference a supplied page and a quote present in that page. Answers similarly require retrieved chunk IDs and quotes. Neither check proves semantic entailment. Model output is not promoted into canonical case metadata.

## Retrieval

BM25 is an explicit, inspectable baseline. It loads the small corpus into memory and applies case/source filters before ranking. It is appropriate for the included demonstration, not millions of records.

Semantic indexing uses Voyage document embeddings; search uses query embeddings. Cache identity includes model, dimension, input type and text. Pinecone stores IDs and lightweight metadata, while SQL remains authoritative for content and citations. A query filters the embedding model/dimension and source/case; results are hydrated only if their chunk IDs still exist in the filtered SQL corpus. Stale vectors can reduce recall but cannot reintroduce replaced text. Obsolete-vector deletion and per-document indexing checkpoints are future work. Changing models requires a separate namespace; chunk IDs alone do not identify the embedding model.

## Failure and operating model

The implementation assumes one writer. It does not provide distributed job leases, concurrent ingestion locks, a durable queue or automatic scheduled retries. A document replacement is transactional; API calls and filesystem writes are outside that transaction. Unreferenced immutable files can remain after a database failure. An incomplete indexing run can be retried: cached embeddings avoid repeated embedding calls and Pinecone upserts are idempotent by vector ID.

The web server binds to loopback and exposes no enrichment endpoint. Missing keys are explicit configuration errors; no fallback is represented as a live model result. Generative/embedding POST requests are not automatically retried to avoid accidental duplicate costs. Read requests and idempotent vector operations retry selected transient HTTP statuses, with a capped delay. Provider error bodies and auth headers are not surfaced.

## Next changes for a larger corpus

Use object storage for raw PDFs, a queue with source-aware rate limits and checkpointed pagination, PostgreSQL full-text candidate retrieval, batch indexing with vector cleanup, isolated OCR workers, and a broader labeled evaluation set that distinguishes document relevance from passage/answer correctness. Add extraction entailment review and adversarial prompt-injection tests. Before hosting beyond loopback, add authentication, authorization, query limits, observability and a deliberate public-data policy.

No performance, AWS deployment or compliance claim is inferred from this prototype.
