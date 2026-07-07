# Knowledge Graph and Memory

## Why this matters
Recall is moving toward GraphRAG-style architecture because the goal is not just to find documents; the goal is to understand relationships and help users rediscover forgotten knowledge.

## Graph and memory are related but not the same
- Graph: structure of entities and relationships.
- Memory: what Recall remembers about the user, their preferences, and their history.

## Graph goals
The graph should support:
- entity extraction
- relationship extraction
- graph traversal
- community detection
- topic neighborhoods
- hub discovery
- bridge discovery

## Memory goals
Memory should support:
- working memory
- semantic memory
- episodic memory
- user preference memory
- long-term memory

## The right order
Do not jump to memory libraries or graph databases before the system has a clear schema and policy.

## Recommended graph evolution
### Step 1
Keep graph projections in the current database layer.

### Step 2
Extract typed entities and relations.

### Step 3
Build community summaries and neighborhood views.

### Step 4
Use graph-aware retrieval.

### Step 5
Only then consider a dedicated graph database if query complexity demands it.

## Recommended memory evolution
### Step 1
Define memory types in Recall itself.

### Step 2
Decide what should be remembered, summarized, or forgotten.

### Step 3
Create policies for consolidating memory from items, conversations, and branches.

### Step 4
Consider Mem0, Zep, or Letta only if the custom memory policy starts becoming messy.

## GraphRAG direction
GraphRAG is valuable as a direction because it emphasizes:
- graph extraction
- community detection
- summarization by neighborhood
- retrieval over relationships, not just chunks

That matches Recall's long-term goal better than chunk-only RAG.

## What custom implementation should own
- entity schema
- relation schema
- traversal policy
- memory policy
- branch semantics
- community scoring
- knowledge health metrics

## What libraries can assist with
- graph extraction helpers
- memory abstraction
- community detection tooling
- summarization helpers

## What not to do too early
- do not treat the graph as a separate product
- do not migrate to Neo4j just because graph sounds right
- do not add memory abstraction before memory behavior is understood

## Success definition
Recall's graph and memory systems are successful when:
- related knowledge is surfaced naturally
- user preferences are remembered safely
- stale or duplicate memory does not dominate
- graph traversal helps answer questions the user didn't explicitly ask
