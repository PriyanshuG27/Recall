# Retrieval Roadmap

## Why retrieval matters
Recall is only as good as the answer it can surface. Retrieval quality is therefore a product feature, not an internal detail.

## Current strength
The current hybrid approach is a good base:
- dense semantic search
- lexical/trigram style retrieval
- custom ranking and fusion
- query-time AI assistance

## What should be added

### 1. Metadata filtering
Users should be able to restrict retrieval by:
- source type
- date
- tag
- topic
- branch
- confidence
- sensitivity

### 2. Parent document retrieval
Sometimes a chunk is too small. Retrieval should be able to bubble up to its parent section or parent document.

### 3. Recursive retrieval
When one result points to another relevant document or section, the system should be able to follow that path deliberately.

### 4. Reranking
Reranking is one of the highest leverage retrieval improvements. It can dramatically improve answer quality without changing the storage layer.

### 5. Query rewriting
Rewrite noisy queries into better search intent before retrieval.

### 6. Context compression
Pass only the truly relevant context to the model instead of dumping too much text.

## Retrieval pipeline target
```mermaid
flowchart LR
Q[Query] --> R1[Rewrite]
R1 --> R2[Hybrid candidate retrieval]
R2 --> R3[Rerank]
R3 --> R4[Parent/recursive expansion]
R4 --> R5[Context compression]
R5 --> A[LLM answer]
```

## Role of libraries
### LlamaIndex
Useful for recursive retrieval and retrieval composition if custom code becomes complex.

### Haystack
Useful if the retrieval pipeline becomes component-heavy and needs clean orchestration.

### DSPy
Useful later for optimizing the retrieval-answering program based on evaluation data.

## What should remain custom
- scoring strategy
- hybrid fusion rules
- metadata policy
- branch-aware retrieval
- graph-aware retrieval routing
- context compression policy

## What not to do
- do not replace the whole retrieval system with a framework
- do not add recursive retrieval before the basic hybrid path is stable
- do not adopt a dedicated vector DB just to feel modern

## Priority order
1. Reranking
2. Metadata filtering
3. Parent retrieval
4. Query rewriting
5. Context compression
6. Recursive retrieval
7. Graph-aware retrieval
8. Retrieval optimization with DSPy

## What good looks like
A user should feel that Recall finds the right thing quickly, explains why it found it, and only sends the necessary context onward.
