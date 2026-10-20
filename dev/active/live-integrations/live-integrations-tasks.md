Last Updated: 2026-10-19

# Live integrations — tasks

- [x] Reproduce tests and federal ingestion locally (31 passed; hashes and counts match)
- [x] Verify Claude/Voyage/Pinecone request contracts against current docs (Pinecone query pending live)
- [x] NYSCEF doc 35 restored via `courtsignal browser-fetch` (2026-10-19): 2 cases / 3 docs / 53 pages / 94 chunks, byte-identical to recorded; keyword eval 6/6 rank 1; rerun all unchanged
- [ ] Publish hash-pinned archive copy (GitHub release `corpus-v1`) and add `fallback_url` to examples/demo.json; awaiting user approval to publish; verify the release redirect host and narrow PUBLIC_HOSTS
- [x] Scripted walkthrough recorded to docs/demo.gif (Playwright); fixed .checks line breaks found in review
- [ ] Manual browser walkthrough of offline docs/demo.html
- [ ] User adds ANTHROPIC_API_KEY to .env; bounded `enrich` on doc 54 (3 pages); record
- [ ] Bounded `answer` (keyword mode); record
- [x] Voyage + Pinecone live (2026-10-19): 94/94 upserted; semantic eval 6/6 rank 1; docs/live-semantic-validation.json. 32-chunk batches hit HTTP 429 without a Voyage payment method; added --batch-size/--pause
- [ ] Rotate Voyage and Pinecone keys (pasted in chat)
- [ ] Optional: RECAP with CourtListener token on one docket, limit 2
- [ ] Update README execution status with actual results only
