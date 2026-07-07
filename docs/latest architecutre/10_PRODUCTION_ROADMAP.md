# Production Roadmap

## v1.0 — Ship the stable core
Ship only what already exists plus the critical hardening work:
- branching integration
- AI cascade stabilization
- security review
- logging overhaul
- analytics
- testing
- deployment

## v1.1 — Stabilize
Use real usage to fix:
- crashes
- slow endpoints
- worker retries
- ingestion failures
- search edge cases

## v1.2 — Ingestion quality
Improve:
- unified document parsing
- better OCR/layout handling
- metadata extraction
- semantic chunking
- hierarchical chunking

## v1.3 — Retrieval quality
Add:
- reranking
- parent-child retrieval
- metadata filters
- query rewriting
- context compression
- recursive retrieval where needed

## v2.0 — Knowledge depth
Add:
- entity extraction
- relation extraction
- graph projection
- community detection
- typed memory
- memory policy

## v3.0 — Infrastructure specialization
Only if demanded by scale:
- vector DB migration
- graph DB migration
- workflow engine
- tracing stack
- more specialized infra

## Rule for future versions
Do not move to the next layer until the current layer is measurably useful.
