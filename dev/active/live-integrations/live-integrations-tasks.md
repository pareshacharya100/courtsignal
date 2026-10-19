Last Updated: 2026-10-19

# Live integrations — tasks

- [x] Reproduce tests and federal ingestion locally (31 passed; hashes and counts match)
- [x] Verify Claude/Voyage/Pinecone request contracts against current docs (Pinecone query pending live)
- [ ] User downloads NYSCEF doc 35 in a browser; add a hash-verified local-file ingest option and test; re-run full ingest (2 cases / 3 docs / 53 pages / 94 chunks)
- [ ] Browser walkthrough of live explorer and offline demo
- [ ] User adds ANTHROPIC_API_KEY to .env; bounded `enrich` on doc 54 (3 pages); record
- [ ] Bounded `answer` (keyword mode); record
- [ ] User creates Pinecone index (1024, cosine) and adds Voyage/Pinecone keys; `index`, one semantic search, `evaluate --mode semantic`; record
- [ ] Optional: RECAP with CourtListener token on one docket, limit 2
- [ ] Update README execution status with actual results only
