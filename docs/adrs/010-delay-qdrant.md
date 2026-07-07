# ADR 010: Delay Qdrant

## Context
Vector databases are critical for RAG. Dedicated engines like Qdrant offer Rust-based speed and advanced filtering.

## Decision
Delay the adoption of Qdrant. Exclusively use `pgvector` inside PostgreSQL.

## Consequences
*   Vector embeddings live in the exact same table as the chunk metadata.
*   Cascading deletes (when a user deletes an item, all its vectors are instantly deleted) are handled natively by Postgres foreign keys.

## Alternatives
*   **Qdrant / Pinecone / Chroma:** Exceptional performance, but requires dual-write synchronization (writing to Postgres, then writing to Qdrant).

## Tradeoffs
Slightly slower vector retrieval at massive scale in exchange for absolute data consistency and zero split-brain deletion bugs.

## Future review trigger
If `pgvector` HNSW index memory requirements exceed the cost-efficient RAM limits of our Neon PostgreSQL tier.
