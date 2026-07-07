# Library & Architecture Decisions (03_LIBRARY_DECISIONS)

**Purpose:** This document evaluates the 39 researched technologies and makes a definitive adoption ruling based on Recall's custom architecture constraints.

---

## Part 1: Ingestion, Orchestration & Databases

### 1. Unstructured
1. **Problem:** Extracts text/layout from PDFs and complex docs.
2. **Recall solves this:** Poorly (naive PyPDF text extraction).
3. **Replaces:** Custom text scraping glue code.
4. **Fits:** Ingestion pipeline (pre-chunking).
5. **Code eliminated:** ~200 lines of brittle PDF parsing logic.
6. **Complexity added:** High (heavy library, massive dependencies).
7. **Tradeoffs:** Perfect structure vs. high memory usage.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** No (parsing PDFs is a solved, complex problem).
*   **Final Decision:** Adopt.
*   **Reason:** RAG fails without structural document understanding.
*   **Engineering Effort:** 3 days.
*   **Risk:** High (OOM during parsing).
*   **Migration Strategy:** Route PDFs to new Unstructured adapter.

### 2. Haystack
1. **Problem:** End-to-end NLP/RAG orchestration.
2. **Recall solves this:** Yes, via the custom AI Cascade.
3. **Replaces:** Entire `backend/services/ai_cascade/` directory.
4. **Fits:** Replaces the core orchestrator.
5. **Code eliminated:** ~2000 lines.
6. **Complexity added:** High (new DSL/framework lock-in).
7. **Tradeoffs:** Less code vs. zero architectural control.
8. **Adopt?** No.
9. **Timeline:** Never.
10. **Implement ourselves?** Yes (Already done).
*   **Final Decision:** Reject.
*   **Reason:** Recall's cascade is final and custom-built for our memory domain.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 3. LlamaIndex
1. **Problem:** Data frameworks and RAG orchestration.
2. **Recall solves this:** Yes (custom Postgres RAG).
3. **Replaces:** Retrieval pipelines.
4. **Fits:** Search and retrieval.
5. **Code eliminated:** ~500 lines.
6. **Complexity added:** High.
7. **Tradeoffs:** Pre-built algorithms vs. loss of control over the SQL planner.
8. **Adopt?** No.
9. **Timeline:** Never.
10. **Implement ourselves?** Yes.
*   **Final Decision:** Reject.
*   **Reason:** We require absolute control over `user_id` filtering and SQL joins.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 4. DSPy
1. **Problem:** Optimizing LLM prompts programmatically.
2. **Recall solves this:** No (manual Jinja templates).
3. **Replaces:** Jinja prompt templates.
4. **Fits:** AI Cascade pipeline generation.
5. **Code eliminated:** None (replaces prompts with code).
6. **Complexity added:** Very High.
7. **Tradeoffs:** Optimized accuracy vs. complete loss of prompt readability.
8. **Adopt?** No (for now).
9. **Timeline:** V3.
10. **Implement ourselves?** No.
*   **Final Decision:** Delay.
*   **Reason:** Premature optimization. We lack the evaluation datasets required to compile DSPy.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** Revisit when test suites are mature.

### 5. Instructor
1. **Problem:** Guaranteed structured JSON extraction from LLMs.
2. **Recall solves this:** Poorly (brittle regex heuristic repair).
3. **Replaces:** `BaseValidator` regex cleanup logic.
4. **Fits:** `ExecutionEngine` output parsing.
5. **Code eliminated:** ~150 lines of complex string manipulation.
6. **Complexity added:** Low.
7. **Tradeoffs:** Clean Pydantic code vs. reliance on provider's tool-calling capability.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** No (Instructor is lightweight and standard).
*   **Final Decision:** Adopt.
*   **Reason:** Drastically improves structured output reliability for graphs and memory.
*   **Engineering Effort:** 2 days.
*   **Risk:** Low.
*   **Migration Strategy:** Wrap Groq/Gemini clients with Instructor patch.

### 6. Outlines
1. **Problem:** Guaranteed structured generation at the logits level.
2. **Recall solves this:** No.
3. **Replaces:** Instructor/Function calling.
4. **Fits:** Local LLM inference.
5. **Code eliminated:** None.
6. **Complexity added:** Very High (requires hosting vLLM).
7. **Tradeoffs:** Mathematical guarantees vs. massive infrastructure cost.
8. **Adopt?** No.
9. **Timeline:** Future.
10. **Implement ourselves?** No.
*   **Final Decision:** Reject (for now).
*   **Reason:** We rely on cloud APIs (Groq/Gemini). Outlines requires local weight access.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 7. Mem0
1. **Problem:** Persistent user memory layer.
2. **Recall solves this:** Partially (Semantic Hubs).
3. **Replaces:** Custom memory extraction.
4. **Fits:** Graph/Memory pipeline.
5. **Code eliminated:** None (we haven't built explicit memory yet).
6. **Complexity added:** High (opaque third-party layer).
7. **Tradeoffs:** Fast deployment vs. loss of graph ownership.
8. **Adopt?** No.
9. **Timeline:** Never.
10. **Implement ourselves?** Yes.
*   **Final Decision:** Reject.
*   **Reason:** Recall *is* a memory engine. Outsourcing memory to a black box defeats the product vision.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 8. Neo4j
1. **Problem:** Fast deep graph traversal.
2. **Recall solves this:** Partially (PostgreSQL recursive CTEs).
3. **Replaces:** PostgreSQL `edges` table.
4. **Fits:** Knowledge Graph storage.
5. **Code eliminated:** SQL traversal queries.
6. **Complexity added:** Very High (new database infrastructure).
7. **Tradeoffs:** Unmatched traversal speed vs. massive ops burden.
8. **Adopt?** No.
9. **Timeline:** V3.
10. **Implement ourselves?** N/A (Using Postgres).
*   **Final Decision:** Delay.
*   **Reason:** Postgres can handle 2-hop graph queries fine for V1/V2.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** Migrate edges if Postgres latency exceeds 500ms for graph queries.

### 9. Memgraph
1. **Problem:** High-speed in-memory graph DB.
2. **Recall solves this:** (See Neo4j).
*   **Final Decision:** Reject (If we use a graph DB, Neo4j is safer for enterprise stability).

### 10. FalkorDB
1. **Problem:** LLM-optimized graph DB.
2. **Recall solves this:** (See Neo4j).
*   **Final Decision:** Reject.

### 11. Qdrant
1. **Problem:** Massive scale vector search.
2. **Recall solves this:** Yes (pgvector).
3. **Replaces:** `items_chunks` vector index.
4. **Fits:** Retrieval.
5. **Code eliminated:** SQL vector queries.
6. **Complexity added:** High (second stateful database).
7. **Tradeoffs:** Rust speed vs. split brain data consistency.
8. **Adopt?** No.
9. **Timeline:** Future.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Delay.
*   **Reason:** pgvector is ACID compliant and sufficient until we hit >100M vectors.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** Monitor pgvector latency; migrate if >50ms.

### 12. Chroma
1. **Problem:** Easy local vector storage.
*   **Final Decision:** Reject (pgvector is superior for our cloud PostgreSQL stack).

### 13. pgvector
1. **Problem:** Vector search inside SQL.
2. **Recall solves this:** Yes (already implemented).
3. **Replaces:** External vector DBs.
4. **Fits:** Postgres schema.
5. **Code eliminated:** External API sync logic.
6. **Complexity added:** Low.
7. **Tradeoffs:** Slower than Qdrant at extreme scale vs. perfect ACID consistency.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Adopt (Already in use).
*   **Reason:** The ultimate simplification of the stack. Data and vectors live together.
*   **Engineering Effort:** 0 days.
*   **Risk:** Low.
*   **Migration Strategy:** Maintain current HNSW indices.
## Part 2: Observability, Agents & Embeddings

### 14. Structlog
1. **Problem:** Parsing text logs in production is impossible.
2. **Recall solves this:** No (currently using standard prints).
3. **Replaces:** Standard Python `logging`.
4. **Fits:** Application-wide logging.
5. **Code eliminated:** N/A (Standardizes logs).
6. **Complexity added:** Low.
7. **Tradeoffs:** JSON verbosity vs. machine readability.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** Required for Datadog/CloudWatch integration.
*   **Engineering Effort:** 1 day.
*   **Risk:** Low.
*   **Migration Strategy:** Global search/replace of `logging` with `structlog`.

### 15. Sentry
1. **Problem:** Missing visibility on unhandled exceptions in workers.
2. **Recall solves this:** No.
3. **Replaces:** Checking docker logs manually.
4. **Fits:** Application entry points.
5. **Code eliminated:** N/A.
6. **Complexity added:** Low.
7. **Tradeoffs:** Minimal latency vs. complete error visibility.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** Crucial for identifying silent failures in background tasks.
*   **Engineering Effort:** 1 day.
*   **Risk:** Low (ensure PII is scrubbed).
*   **Migration Strategy:** Init Sentry in `main.py` and `worker.py`.

### 16. OpenTelemetry
1. **Problem:** Distributed tracing across microservices.
2. **Recall solves this:** No.
3. **Replaces:** Basic request IDs.
4. **Fits:** API/Worker tracing.
5. **Code eliminated:** Custom `request_id` context vars.
6. **Complexity added:** Very High.
7. **Tradeoffs:** Vendor neutrality vs. massive boilerplate.
8. **Adopt?** No.
9. **Timeline:** Future.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Reject (for now).
*   **Reason:** Recall is a monolith. A simple `request_id` ContextVar is sufficient for V1.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 17. Promptfoo
1. **Problem:** Preventing prompt regressions.
2. **Recall solves this:** No (no prompt evals exist).
3. **Replaces:** Manual vibe-checking.
4. **Fits:** CI/CD pipeline.
5. **Code eliminated:** N/A.
6. **Complexity added:** Medium (writing test sets).
7. **Tradeoffs:** Slower CI times vs. mathematical confidence in AI output.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** AI Cascade updates are dangerous without regression testing.
*   **Engineering Effort:** 5 days (building datasets).
*   **Risk:** Low.
*   **Migration Strategy:** Add to GitHub Actions.

### 18. Ragas
1. **Problem:** Evaluating RAG accuracy.
2. **Recall solves this:** No.
*   **Final Decision:** Adopt (V2). Use alongside Promptfoo for RAG-specific evaluation.

### 19. Phoenix
1. **Problem:** AI observability and drift detection.
*   **Final Decision:** Delay. We will evaluate Langfuse first as it requires less local infrastructure.

### 20. Langfuse
1. **Problem:** Visualizing LLM traces, costs, and inputs.
2. **Recall solves this:** Partially (Custom `ai_decision_logs`).
3. **Replaces:** Custom database logging.
4. **Fits:** AI Cascade Execution Engine.
5. **Code eliminated:** ~300 lines of custom SQL inserts.
6. **Complexity added:** Low.
7. **Tradeoffs:** Paying a SaaS vs. building a custom UI for `ai_decision_logs`.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** The UI for tracing nested LLM calls saves hundreds of debugging hours.
*   **Engineering Effort:** 2 days.
*   **Risk:** Medium (Privacy concerns sending traces to SaaS).
*   **Migration Strategy:** Wrap `ExecutionEngine` with Langfuse decorators.

### 21. CrewAI
1. **Problem:** Multi-agent autonomous orchestration.
2. **Recall solves this:** No (Recall is deterministic).
3. **Replaces:** AI Cascade.
4. **Fits:** Background tasks.
5. **Code eliminated:** N/A.
6. **Complexity added:** Extreme.
7. **Tradeoffs:** Cool demos vs. production unreliability.
8. **Adopt?** No.
9. **Timeline:** Never.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Reject.
*   **Reason:** We need a deterministic pipeline (Cascade), not chatty loops.
*   **Engineering Effort:** 0 days.
*   **Risk:** None.
*   **Migration Strategy:** N/A.

### 22. AutoGen
1. **Problem:** Multi-agent orchestration.
*   **Final Decision:** Reject (Same reason as CrewAI).

### 23. LangGraph
1. **Problem:** Graph-based LLM state machines.
*   **Final Decision:** Reject. We own our state in the custom cascade.

### 24. Semantic Kernel
1. **Problem:** Code/LLM integration.
*   **Final Decision:** Reject (Over-engineered for our Python stack).

### 25. GraphRAG (Concept)
1. **Problem:** Answering global queries ("What is this dataset about?").
2. **Recall solves this:** No (naive vector search fails here).
3. **Replaces:** Simple vector search for broad queries.
4. **Fits:** Memory/Graph extraction layer.
5. **Code eliminated:** N/A.
6. **Complexity added:** High.
7. **Tradeoffs:** High extraction cost vs. incredible reasoning capability.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** Yes (Native implementation on Postgres).
*   **Final Decision:** Adopt the *Architecture*, not the Microsoft library.
*   **Reason:** It fits our custom PostgreSQL entity/edge design perfectly.
*   **Engineering Effort:** 10 days.
*   **Risk:** High (Token costs).
*   **Migration Strategy:** Build background community summarizer crons.

### 26. FastEmbed
1. **Problem:** Heavy PyTorch overhead for embedding generation.
2. **Recall solves this:** No (Currently uses SentenceTransformers).
3. **Replaces:** PyTorch / SentenceTransformers.
4. **Fits:** Ingestion worker.
5. **Code eliminated:** PyTorch setup code.
6. **Complexity added:** Low.
7. **Tradeoffs:** Limited model support vs. blazing CPU speed.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** Massively reduces RAM footprint for background workers.
*   **Engineering Effort:** 2 days.
*   **Risk:** Low.
*   **Migration Strategy:** Swap SentenceTransformers for FastEmbed ONNX runtime.
## Part 3: Retrieval Models & Chunking Strategies

### 27. Voyage
1. **Problem:** Need highly accurate embeddings.
2. **Recall solves this:** Yes (Local MiniLM).
3. **Replaces:** Local embedding models.
4. **Fits:** Ingestion.
5. **Code eliminated:** Local inference code.
6. **Complexity added:** Low.
7. **Tradeoffs:** API cost/latency vs. higher MTEB score.
8. **Adopt?** No.
9. **Timeline:** Maybe (If local fails).
10. **Implement ourselves?** N/A.
*   **Final Decision:** Reject for now.
*   **Reason:** Local BGE/MiniLM models are free and sufficient for V1.
*   **Engineering Effort:** 0 days.

### 28. Jina Embeddings
1. **Problem:** 8k context embeddings.
*   **Final Decision:** Reject. Massive chunks dilute search precision.

### 29. BGE (BAAI)
1. **Problem:** MiniLM is fast but losing ground on accuracy.
2. **Recall solves this:** Yes (MiniLM).
3. **Replaces:** MiniLM-L6-v2.
4. **Fits:** Ingestion embedding step.
5. **Code eliminated:** N/A.
6. **Complexity added:** None (Drop-in replacement).
7. **Tradeoffs:** Slightly larger model vs. top-tier accuracy.
8. **Adopt?** Yes.
9. **Timeline:** V1.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Adopt.
*   **Reason:** Best open-source embedding model for standard sizes.
*   **Engineering Effort:** 1 day (Regenerate vectors).
*   **Risk:** Medium (Requires re-embedding entire DB).
*   **Migration Strategy:** Backfill script to re-embed `item_chunks`.

### 30. ColBERT
1. **Problem:** Dense vectors miss exact keywords.
2. **Recall solves this:** Yes (via Hybrid Trigram search).
3. **Replaces:** Trigrams.
4. **Fits:** Search layer.
5. **Code eliminated:** SQL Trigram queries.
6. **Complexity added:** Extreme.
7. **Tradeoffs:** Best possible accuracy vs. 50x storage bloat.
8. **Adopt?** No.
9. **Timeline:** Future.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Reject.
*   **Reason:** Storage costs in Postgres would be unjustifiable for a personal OS.
*   **Engineering Effort:** 0 days.

### 31. Nomic
1. **Problem:** Fully open training data embeddings.
*   **Final Decision:** Delay. BGE is more proven for our immediate needs.

### 32. Mixedbread (Cross-Encoders)
1. **Problem:** RRF fusion is naive and imprecise.
2. **Recall solves this:** Poorly (Mathematical RRF only).
3. **Replaces:** Pure RRF.
4. **Fits:** Retrieval pipeline (Reranking layer).
5. **Code eliminated:** N/A.
6. **Complexity added:** Medium (Local inference on search path).
7. **Tradeoffs:** +200ms latency vs. massive precision boost.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** No.
*   **Final Decision:** Adopt.
*   **Reason:** Reranking is the easiest way to immediately improve RAG answers.
*   **Engineering Effort:** 3 days.
*   **Risk:** Medium (Search latency increase).
*   **Migration Strategy:** Add reranker step after Postgres returns top 20.

### 33. BM25
1. **Problem:** Keyword exact match.
2. **Recall solves this:** Yes (`pg_trgm`).
3. **Replaces:** Trigrams.
4. **Fits:** Search layer.
5. **Code eliminated:** N/A.
6. **Complexity added:** Low.
7. **Tradeoffs:** Lexical match vs. Trigram fuzzy match.
8. **Adopt?** Maybe.
9. **Timeline:** V2.
10. **Implement ourselves?** Yes (via Postgres `tsvector`).
*   **Final Decision:** Evaluate.
*   **Reason:** Postgres `tsvector` might outperform `pg_trgm` for long documents.
*   **Engineering Effort:** 2 days to benchmark.

### 34. Hybrid Retrieval
1. **Problem:** Capturing both meaning and exact words.
*   **Final Decision:** Adopt (Currently implemented and mandated).

### 35. Recursive Retrieval (Parent/Child)
1. **Problem:** Small chunks lose context; large chunks dilute vectors.
2. **Recall solves this:** No (Static chunking).
3. **Replaces:** Static chunk retrieval.
4. **Fits:** Search & DB schema.
5. **Code eliminated:** N/A.
6. **Complexity added:** Medium.
7. **Tradeoffs:** Extra DB lookup vs. perfect context windows.
8. **Adopt?** Yes.
9. **Timeline:** V2.
10. **Implement ourselves?** Yes.
*   **Final Decision:** Adopt natively.
*   **Reason:** Passing parent documents to the LLM drastically reduces hallucinations.
*   **Engineering Effort:** 4 days.
*   **Risk:** Low.
*   **Migration Strategy:** Add `parent_id` to `item_chunks`.

### 36. Parent Retrieval
*   **Final Decision:** Adopt (Same as above).

### 37. Late Chunking
1. **Problem:** Context loss at chunk boundaries.
2. **Recall solves this:** No.
*   **Final Decision:** Delay (Requires specialized embedding models, too bleeding edge).

### 38. Semantic Chunking
1. **Problem:** Arbitrary character splits break thoughts.
2. **Recall solves this:** No.
3. **Replaces:** RecursiveCharacterTextSplitter.
4. **Fits:** Ingestion layer.
5. **Code eliminated:** Old Langchain splitter.
6. **Complexity added:** High.
7. **Tradeoffs:** High embedding cost vs. perfect chunk semantic coherence.
8. **Adopt?** No.
9. **Timeline:** Maybe.
10. **Implement ourselves?** N/A.
*   **Final Decision:** Reject (for V1).
*   **Reason:** Embedding every sentence to find split points is too computationally expensive for our background workers right now.
*   **Engineering Effort:** 0 days.

### 39. Adaptive Chunking
1. **Problem:** Query needs dictate chunk size.
2. **Recall solves this:** No.
*   **Final Decision:** Reject (Too academic and complex for current Postgres schema).
