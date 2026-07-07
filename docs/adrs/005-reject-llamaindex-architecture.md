# ADR 005: Reject Full LlamaIndex Architecture

## Context
LlamaIndex provides excellent frameworks for document chunking, indexing, and advanced RAG routing. 

## Decision
Reject LlamaIndex as the core orchestrator. We will build our custom Retrieval pipeline directly against PostgreSQL.

## Consequences
*   We manually manage structural chunking (via Unstructured) and vector inserts.
*   We manually write SQL queries for RRF fusion and recursive parent retrieval.

## Alternatives
*   **LlamaIndex:** Beautiful abstractions for complex RAG.

## Tradeoffs
LlamaIndex obscures the raw database queries. In a multi-tenant system like Recall, we must have absolute, transparent control over the `WHERE user_id = $1` filters at the lowest SQL level to prevent catastrophic cross-user data leaks.

## Future review trigger
V2. We will not adopt the framework, but we will continuously review LlamaIndex's open-source algorithms to adapt their math (e.g., adaptive chunking) into our native Python pipeline.
