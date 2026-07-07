# ADR 009: Delay Neo4j

## Context
The architecture is moving toward GraphRAG (extracting entities and relations). Graph traversals are highly optimized in dedicated graph databases.

## Decision
Delay the adoption of Neo4j. Build the V1 Knowledge Graph natively in PostgreSQL using `entities` and `edges` tables.

## Consequences
*   We avoid provisioning, securing, and maintaining a JVM-based Neo4j cluster.
*   Graph traversals must be written using Recursive CTEs in SQL.

## Alternatives
*   **Neo4j / Memgraph:** Blazing fast graph native capabilities.

## Tradeoffs
Operational simplicity is prioritized over theoretical deep-traversal speed. Most GraphRAG queries for a personal OS only require 1-hop or 2-hop traversals, which PostgreSQL handles perfectly well.

## Future review trigger
When PostgreSQL Recursive CTE latency for 2-hop graph queries consistently exceeds 500ms, or when we require complex path-finding algorithms (e.g., shortest path between 5 entities).
