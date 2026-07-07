# ADR 001: Keep PostgreSQL

## Context
Recall requires durable storage for relational user data, dense vector embeddings for semantic search, and edge relationships for graph traversals. Introducing separate databases for each data type (e.g., MySQL + Pinecone + Neo4j) introduces split-brain consistency issues, complex backup strategies, and high operational overhead.

## Decision
Keep Neon Serverless PostgreSQL as the single source of truth for all data, utilizing `pgvector` for HNSW vector search and `pg_trgm` for fuzzy text matching.

## Consequences
*   Zero split-brain data consistency issues.
*   Backups and point-in-time recovery cover vectors, graphs, and users simultaneously.
*   Requires careful indexing (composite indices) to ensure metadata filtering does not degrade vector search performance.

## Alternatives
*   **Vector DB (Qdrant/Pinecone):** Better extreme-scale vector performance, but breaks relational ACID guarantees.
*   **MongoDB:** Poor relational integrity for strict tenant isolation (`user_id`).

## Tradeoffs
Operational simplicity and perfect data consistency are prioritized over the raw extreme-scale performance of dedicated NoSQL/Vector engines.

## Future review trigger
When the `item_chunks` table exceeds 50-100 million vectors, or if the HNSW indices exceed the available RAM on the PostgreSQL instance, forcing heavy disk swapping.
