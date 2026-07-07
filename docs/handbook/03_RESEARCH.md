# Research & Technology Evaluation (02_RESEARCH)

**Purpose:** This document exhaustively researches every technology and architectural pattern evaluated for the Recall project. It answers definitively whether Recall should adopt them and when.

---

## Part 1: Ingestion, Orchestration & Databases

### 1. Unstructured
*   **Purpose:** Extracting structured text/layout from unstructured files (PDF, HTML, DOCX).
*   **How it works:** Uses ML models (like YOLOX) and heuristics to identify titles, tables, and paragraphs.
*   **Architecture:** Python library, can run locally or via API.
*   **Companies using it:** LangChain, LlamaIndex, many enterprise RAG pipelines.
*   **Advantages:** Preserves document layout (tables, headings) unlike naive text extractors.
*   **Disadvantages:** Heavy dependencies, slow on complex PDFs, OOM risks.
*   **Maintenance burden:** High (frequent updates, large model weights).
*   **Performance:** Slow on PDFs without GPU. Fast on HTML/TXT.
*   **Complexity:** Medium.
*   **Cost:** Free (local) or paid (API).
*   **License:** Apache 2.0.
*   **Open Source status:** Fully open source.
*   **Alternatives:** PyMuPDF, pdfplumber, AWS Textract.
*   **Integration points:** Ingestion pipeline.
*   **Examples:** `partition_pdf("file.pdf", strategy="hi_res")`
*   **Should Recall use it?** V1 (Crucial for deep document understanding).

### 2. Haystack
*   **Purpose:** End-to-end NLP and RAG framework.
*   **How it works:** Connects document stores, retrievers, and LLMs via pipelines.
*   **Architecture:** Node-and-edge pipeline architecture.
*   **Companies using it:** Deepset, Airbus, Alcatel-Lucent.
*   **Advantages:** Highly modular, enterprise-focused.
*   **Disadvantages:** Steep learning curve, less hype/community momentum than LangChain.
*   **Maintenance burden:** Medium.
*   **Performance:** Depends on underlying models.
*   **Complexity:** High.
*   **Cost:** Free.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** LlamaIndex, LangChain.
*   **Integration points:** Core AI orchestrator.
*   **Examples:** `Pipeline().add_node(...)`
*   **Should Recall use it?** Never (Recall's AI Cascade is final and custom).

### 3. LlamaIndex
*   **Purpose:** Data framework for LLM applications.
*   **How it works:** Ingests data, creates indices (vector, tree, keyword), and handles querying.
*   **Architecture:** Ingestion engines -> Indices -> Query Engines.
*   **Companies using it:** Uber, heterogeneous startups.
*   **Advantages:** Excellent data connectors, great out-of-the-box RAG algorithms.
*   **Disadvantages:** Abstractions can become leaky; hard to debug deep pipeline errors.
*   **Maintenance burden:** Medium.
*   **Performance:** Fast, but abstraction overhead exists.
*   **Complexity:** Medium to High.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Haystack, LangChain.
*   **Integration points:** Retrieval and chunking.
*   **Examples:** `VectorStoreIndex.from_documents(docs)`
*   **Should Recall use it?** Never (Replaced by our custom postgres retrieval pipeline, though we may steal its theoretical algorithms).

### 4. DSPy
*   **Purpose:** Programming framework for optimizing language model prompts.
*   **How it works:** Replaces manual prompt engineering with compiled, optimized multi-stage prompt generation based on metrics.
*   **Architecture:** Modules (like PyTorch) and Optimizers (Teleprompters).
*   **Companies using it:** Databricks, researchers.
*   **Advantages:** Eliminates prompt tweaking; optimizes automatically for specific LLMs.
*   **Disadvantages:** Very academic, steep learning curve, hard to debug optimized prompts.
*   **Maintenance burden:** High (needs evaluation datasets).
*   **Performance:** Can drastically improve LLM accuracy.
*   **Complexity:** Very High.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Manual prompt engineering, Promptfoo.
*   **Integration points:** Prompt generation inside AI Cascade.
*   **Examples:** `dspy.ChainOfThought("question -> answer")`
*   **Should Recall use it?** V3 (Requires mature evaluation datasets first).

### 5. Instructor
*   **Purpose:** Structured data extraction from LLMs using Pydantic.
*   **How it works:** Patches OpenAI/Groq clients to force them to return JSON matching a Pydantic schema using function calling.
*   **Architecture:** Lightweight wrapper around LLM SDKs.
*   **Companies using it:** Widespread in modern AI startups.
*   **Advantages:** Extremely simple, typed, native Python validation.
*   **Disadvantages:** Relies heavily on the LLM's native function calling capability.
*   **Maintenance burden:** Low.
*   **Performance:** Fast.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Outlines, Marvin.
*   **Integration points:** AI Cascade `ExecutionEngine`.
*   **Examples:** `client.chat.completions.create(..., response_model=UserSchema)`
*   **Should Recall use it?** V1 (Perfect replacement for our manual JSON regex heuristics).

### 6. Outlines
*   **Purpose:** Guided text generation and structured prompting.
*   **How it works:** Modifies the logits of the LLM at the inference engine level (vLLM) to guarantee valid JSON/Regex output.
*   **Architecture:** Integrates with local inference servers.
*   **Companies using it:** HuggingFace ecosystem, local AI deployments.
*   **Advantages:** Mathematical guarantee of schema adherence.
*   **Disadvantages:** Requires control over the inference engine (cannot be used with standard Groq/Gemini APIs).
*   **Maintenance burden:** High (requires local model hosting).
*   **Performance:** Extremely fast local inference.
*   **Complexity:** High.
*   **Cost:** Free (but high compute cost).
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Instructor, LMQL.
*   **Integration points:** Local fallback models.
*   **Examples:** `outlines.generate.json(model, Schema)`
*   **Should Recall use it?** Future (Only if we move to self-hosted models via Modal/vLLM).

### 7. Mem0
*   **Purpose:** Memory layer for personalized AI assistants.
*   **How it works:** Automatically extracts, stores, and retrieves user facts across sessions.
*   **Architecture:** Vector DB + LLM extraction pipelines.
*   **Companies using it:** Emerging AI companions.
*   **Advantages:** Out-of-the-box personalization.
*   **Disadvantages:** Black box memory management, hard to customize the extraction schema.
*   **Maintenance burden:** Low.
*   **Performance:** Fast.
*   **Complexity:** Low.
*   **Cost:** Paid API or Open Source.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Zep, custom PostgreSQL memory.
*   **Integration points:** Memory module.
*   **Examples:** `m.add("I like coffee", user_id="alice")`
*   **Should Recall use it?** Never (We own the memory graph natively in PostgreSQL).

### 8. Neo4j
*   **Purpose:** Native Graph Database.
*   **How it works:** Stores data as nodes and edges using property graph model, queried via Cypher.
*   **Architecture:** Dedicated graph engine, JVM based.
*   **Companies using it:** Comcast, eBay, NASA.
*   **Advantages:** Unmatched traversal speed for deep networks.
*   **Disadvantages:** Separate infrastructure to maintain, complex Cypher language, expensive.
*   **Maintenance burden:** High.
*   **Performance:** Excellent for >3 hop traversals.
*   **Complexity:** High.
*   **Cost:** Expensive (Enterprise) or Free (Community).
*   **License:** GPLv3 / Commercial.
*   **Open Source status:** Open core.
*   **Alternatives:** Memgraph, PostgreSQL (recursive CTEs).
*   **Integration points:** Knowledge Graph persistence.
*   **Examples:** `MATCH (a)-[:KNOWS]->(b) RETURN b`
*   **Should Recall use it?** V3 (Only if PostgreSQL graph queries become a proven bottleneck).

### 9. Memgraph
*   **Purpose:** In-memory Graph Database.
*   **How it works:** C++ based, Cypher compatible, optimized for real-time analytics.
*   **Architecture:** In-memory, disk-backed.
*   **Companies using it:** Cybersecurity and fintech startups.
*   **Advantages:** Significantly faster than Neo4j for real-time writes.
*   **Disadvantages:** Smaller community, still requires separate infrastructure.
*   **Maintenance burden:** High.
*   **Performance:** Ultra-low latency.
*   **Complexity:** High.
*   **Cost:** Enterprise / Community.
*   **License:** BSL.
*   **Open Source status:** Source available.
*   **Alternatives:** Neo4j, FalkorDB.
*   **Integration points:** Knowledge Graph.
*   **Examples:** Cypher queries.
*   **Should Recall use it?** Never (If we move to graph DBs, Neo4j is safer; if not, stick to PostgreSQL).

### 10. FalkorDB
*   **Purpose:** LLM-focused Graph Database (formerly RedisGraph).
*   **How it works:** Uses sparse matrices for fast graph traversal.
*   **Architecture:** Standalone DB or Redis module.
*   **Companies using it:** AI orchestration frameworks.
*   **Advantages:** Integrates well with AI pipelines, extremely fast.
*   **Disadvantages:** Niche, uncertain long-term enterprise adoption.
*   **Maintenance burden:** Medium.
*   **Performance:** Excellent.
*   **Complexity:** Medium.
*   **Cost:** Paid cloud / Open source.
*   **License:** SSPL.
*   **Open Source status:** Source available.
*   **Alternatives:** Neo4j, Memgraph.
*   **Integration points:** Knowledge Graph.
*   **Examples:** Cypher queries.
*   **Should Recall use it?** Never.

### 11. Qdrant
*   **Purpose:** High-performance Vector Database.
*   **How it works:** Rust-based, optimized for dense vector search and payload filtering.
*   **Architecture:** Distributed vector engine.
*   **Companies using it:** Grok (xAI), Discord.
*   **Advantages:** Incredible speed, strict Rust safety, great filtering.
*   **Disadvantages:** Requires maintaining a second database alongside Postgres.
*   **Maintenance burden:** Medium.
*   **Performance:** Top tier.
*   **Complexity:** Medium.
*   **Cost:** Cloud or free self-hosted.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Pinecone, Milvus, pgvector.
*   **Integration points:** Retrieval.
*   **Examples:** `qdrant.search(collection, vector)`
*   **Should Recall use it?** Future (Only if we exceed 100M+ vectors and pgvector degrades).

### 12. Chroma
*   **Purpose:** AI-native open-source vector database.
*   **How it works:** Python/TypeScript focused, runs embedded or client/server.
*   **Architecture:** SQLite/DuckDB backed embedded engine.
*   **Companies using it:** Countless AI prototypes and startups.
*   **Advantages:** Trivial to set up, native to Langchain/LlamaIndex.
*   **Disadvantages:** Struggles at massive production scale compared to Qdrant/Milvus.
*   **Maintenance burden:** Low.
*   **Performance:** Good for small/medium datasets.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Qdrant, pgvector.
*   **Integration points:** Retrieval.
*   **Examples:** `chroma_client.create_collection("docs")`
*   **Should Recall use it?** Never (pgvector solves our needs with better transactional guarantees).

### 13. pgvector
*   **Purpose:** Vector similarity search for PostgreSQL.
*   **How it works:** C extension adding HNSW and IVFFlat index types to Postgres.
*   **Architecture:** Resides entirely inside the Postgres instance.
*   **Companies using it:** Supabase, Neon, widespread adoption.
*   **Advantages:** Zero new infrastructure, ACID compliance, joins with relational data.
*   **Disadvantages:** Filtering + Vector Search can be tricky to optimize (requires composite indices).
*   **Maintenance burden:** Zero (managed by Neon).
*   **Performance:** Sub-10ms for millions of rows with HNSW.
*   **Complexity:** Low.
*   **Cost:** Included in DB compute.
*   **License:** PostgreSQL License.
*   **Open Source status:** Open source.
*   **Alternatives:** Qdrant, Pinecone.
*   **Integration points:** Core Database.
*   **Examples:** `ORDER BY embedding <=> '[0.1, ...]' LIMIT 5`
*   **Should Recall use it?** V1 (Currently in use and absolutely critical).
## Part 2: Observability, Agents & Embeddings

### 14. Structlog
*   **Purpose:** Structured JSON logging for Python.
*   **How it works:** Wraps standard library logging to output machine-readable JSON.
*   **Architecture:** Pipeline of processors (e.g., add timestamp, format JSON).
*   **Companies using it:** Stripe, modern Python web stacks.
*   **Advantages:** Makes logs searchable in Datadog/CloudWatch; prevents string-parsing nightmares.
*   **Disadvantages:** Slight learning curve for processor configuration.
*   **Maintenance burden:** Very Low.
*   **Performance:** Highly optimized.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** MIT/Apache.
*   **Open Source status:** Open source.
*   **Alternatives:** Python `logging` with custom JSON formatters, Loguru.
*   **Integration points:** Core observability layer.
*   **Examples:** `logger.info("event", user_id=1)`
*   **Should Recall use it?** V1 (Critical for production debugging).

### 15. Sentry
*   **Purpose:** Application performance monitoring and error tracking.
*   **How it works:** SDK intercepts unhandled exceptions and ships stack traces to the cloud.
*   **Architecture:** Python SDK hooks into sys.excepthook and FastAPI middlewares.
*   **Companies using it:** GitHub, Disney, practically everyone.
*   **Advantages:** Real-time alerting, stack trace aggregation, performance tracing.
*   **Disadvantages:** Can leak PII if not scrubbed properly.
*   **Maintenance burden:** Low.
*   **Performance:** Async, low overhead.
*   **Complexity:** Low.
*   **Cost:** Paid (SaaS).
*   **License:** Business Source License.
*   **Open Source status:** Source available / self-hostable.
*   **Alternatives:** Rollbar, Datadog APM.
*   **Integration points:** FastAPI and Worker entry points.
*   **Examples:** `sentry_sdk.init(dsn="...")`
*   **Should Recall use it?** V1 (Mandatory for production health).

### 16. OpenTelemetry
*   **Purpose:** Standardized distributed tracing and metrics.
*   **How it works:** Instruments code to emit spans and traces across microservices.
*   **Architecture:** SDKs push to a Collector, which exports to Jaeger/Datadog.
*   **Companies using it:** Massive enterprises, microservice architectures.
*   **Advantages:** Vendor agnostic, incredibly detailed traces.
*   **Disadvantages:** Extremely complex to set up; overkill for monoliths.
*   **Maintenance burden:** High.
*   **Performance:** Can add network latency if not batched.
*   **Complexity:** Very High.
*   **Cost:** Free (standard), but backend aggregators cost money.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Native Datadog APM, New Relic.
*   **Integration points:** Request spanning.
*   **Examples:** `with tracer.start_as_current_span("AI_Call"):`
*   **Should Recall use it?** Future (Only if we split into multiple microservices).

### 17. Promptfoo
*   **Purpose:** Evaluation framework for LLM prompts and models.
*   **How it works:** Runs test suites against multiple prompts/models and grades them via LLM-as-a-judge or deterministic metrics.
*   **Architecture:** CLI tool / Node.js library.
*   **Companies using it:** AI startups optimizing prompts.
*   **Advantages:** Fast, local, prevents regression on prompt changes.
*   **Disadvantages:** Requires building test sets.
*   **Maintenance burden:** Medium.
*   **Performance:** Fast.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Ragas, DeepEval.
*   **Integration points:** CI/CD testing.
*   **Examples:** `promptfoo eval`
*   **Should Recall use it?** V2 (Crucial for iterating on the AI Cascade safely).

### 18. Ragas
*   **Purpose:** RAG Assessment framework.
*   **How it works:** Evaluates RAG pipelines on metrics like Faithfulness, Answer Relevance, and Context Precision using LLM judges.
*   **Architecture:** Python library.
*   **Companies using it:** Enterprise RAG builders.
*   **Advantages:** Specifically designed for RAG pain points.
*   **Disadvantages:** LLM-as-a-judge is slow and costs money per test run.
*   **Maintenance burden:** Medium.
*   **Performance:** Slow (requires multiple LLM calls).
*   **Complexity:** Medium.
*   **Cost:** Free (but token costs apply).
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** TruLens, Promptfoo.
*   **Integration points:** CI/CD, offline evaluation.
*   **Examples:** `evaluate(dataset, metrics=[faithfulness])`
*   **Should Recall use it?** V2.

### 19. Phoenix (Arize)
*   **Purpose:** AI observability and evaluation platform.
*   **How it works:** Traces LLM calls, maps vector embeddings to find drift, and evaluates RAG.
*   **Architecture:** Local server or cloud platform.
*   **Companies using it:** AI-first enterprises.
*   **Advantages:** Beautiful UI for exploring UMAP embedding drift.
*   **Disadvantages:** Another dashboard to manage.
*   **Maintenance burden:** Medium.
*   **Performance:** Async tracing.
*   **Complexity:** Medium.
*   **Cost:** Free (local) / Paid (cloud).
*   **License:** Apache 2.0 (Core).
*   **Open Source status:** Open core.
*   **Alternatives:** Langfuse, LangSmith.
*   **Integration points:** LLM call tracing.
*   **Examples:** `px.launch_app()`
*   **Should Recall use it?** Maybe (Evaluate against Langfuse).

### 20. Langfuse
*   **Purpose:** Open-source LLM engineering platform (Traces, evals, prompt management).
*   **How it works:** Wraps LLM calls to capture inputs, outputs, latencies, and costs.
*   **Architecture:** Postgres-backed web app + SDKs.
*   **Companies using it:** Vercel, PostHog, YC startups.
*   **Advantages:** Exceptional trace UI, easy to self-host, tracks costs automatically.
*   **Disadvantages:** Replaces our custom `ai_decision_logs`.
*   **Maintenance burden:** Low (if using cloud).
*   **Performance:** Async pushing.
*   **Complexity:** Low.
*   **Cost:** Free tier / Paid.
*   **License:** MIT (SDK), FSL (Server).
*   **Open Source status:** Open core.
*   **Alternatives:** LangSmith, Phoenix.
*   **Integration points:** AI Cascade ExecutionEngine.
*   **Examples:** `langfuse.trace(...)`
*   **Should Recall use it?** V2 (Excellent candidate to replace our custom telemetry logs if we want a GUI).

### 21. CrewAI
*   **Purpose:** Framework for orchestrating role-playing, autonomous AI agents.
*   **How it works:** Defines agents, tasks, and tools, letting them converse and delegate to solve goals.
*   **Architecture:** Python library on top of Langchain.
*   **Companies using it:** Automation startups.
*   **Advantages:** Fun, easy to set up complex multi-agent workflows.
*   **Disadvantages:** Highly non-deterministic, hallucinates often, hard to control in strict production environments.
*   **Maintenance burden:** High (babysitting prompts).
*   **Performance:** Slow (lots of LLM routing chatter).
*   **Complexity:** Medium.
*   **Cost:** High token costs.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** AutoGen, LangGraph.
*   **Integration points:** Specific complex background tasks.
*   **Examples:** `Crew(agents=[researcher, writer])`
*   **Should Recall use it?** Never (Recall requires deterministic, strict cascade orchestration, not autonomous chat loops).

### 22. AutoGen
*   **Purpose:** Multi-agent conversation framework by Microsoft.
*   **How it works:** Agents converse with each other and humans to execute code and solve tasks.
*   **Architecture:** Python library, highly customizable agent classes.
*   **Companies using it:** Microsoft, researchers.
*   **Advantages:** Powerful code execution and human-in-the-loop features.
*   **Disadvantages:** Same as CrewAI—non-deterministic loops are dangerous for basic API backends.
*   **Maintenance burden:** High.
*   **Performance:** Slow.
*   **Complexity:** High.
*   **Cost:** High token costs.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** CrewAI.
*   **Integration points:** None.
*   **Examples:** `user_proxy.initiate_chat(assistant)`
*   **Should Recall use it?** Never.

### 23. LangGraph
*   **Purpose:** Building stateful, multi-actor applications with LLMs.
*   **How it works:** Defines cyclic graphs (state machines) where nodes are LLM calls and edges are conditional logic.
*   **Architecture:** Graph-based state machine framework.
*   **Companies using it:** LangChain ecosystem users.
*   **Advantages:** Highly deterministic compared to CrewAI/AutoGen. Allows cyclic RAG flows.
*   **Disadvantages:** Steep learning curve, locks you into LangChain abstractions.
*   **Maintenance burden:** Medium.
*   **Performance:** Fast (graph routing is minimal overhead).
*   **Complexity:** High.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Custom State Machines (Our AI Cascade).
*   **Integration points:** Orchestration.
*   **Examples:** `StateGraph(AgentState)`
*   **Should Recall use it?** Never (We built the AI Cascade to avoid framework lock-in. We own our state).

### 24. Semantic Kernel
*   **Purpose:** Microsoft's SDK for integrating LLMs with code.
*   **How it works:** Mixes conventional code (native functions) with LLMs (semantic functions) via a planner.
*   **Architecture:** C# / Python SDK.
*   **Companies using it:** Microsoft, Enterprise C# shops.
*   **Advantages:** Enterprise-grade, great C# support.
*   **Disadvantages:** Over-engineered for pure Python stacks.
*   **Maintenance burden:** Medium.
*   **Performance:** Good.
*   **Complexity:** High.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** LangChain, LlamaIndex.
*   **Integration points:** None.
*   **Examples:** `kernel.import_plugin(...)`
*   **Should Recall use it?** Never.

### 25. GraphRAG (Microsoft)
*   **Purpose:** Enhancing RAG with Knowledge Graphs.
*   **How it works:** Uses LLMs to extract a graph from documents, then summarizes communities to answer global queries (e.g., "What is the theme of this dataset?").
*   **Architecture:** Extraction Pipeline -> Graph DB -> Community Summarization -> Query Engine.
*   **Companies using it:** Advanced RAG practitioners.
*   **Advantages:** Solves the "global understanding" problem that naive vector search fails at.
*   **Disadvantages:** Extremely expensive to run the initial extraction over large datasets.
*   **Maintenance burden:** High.
*   **Performance:** Slow ingestion, fast query.
*   **Complexity:** Very High.
*   **Cost:** High token costs during ingestion.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Naive RAG.
*   **Integration points:** Chapter 4 (Knowledge Graph layer).
*   **Examples:** Not an API, but an architectural pattern.
*   **Should Recall use it?** V2 (We are moving toward this architecture, but implementing it natively).

### 26. FastEmbed
*   **Purpose:** Fast, lightweight text embedding generation in Python.
*   **How it works:** Runs ONNX models natively in Python using ONNX Runtime, bypassing PyTorch overhead.
*   **Architecture:** Standalone Python library.
*   **Companies using it:** Qdrant ecosystem.
*   **Advantages:** Blazing fast, no PyTorch dependency, low memory footprint.
*   **Disadvantages:** Only supports specific ONNX-exported models.
*   **Maintenance burden:** Low.
*   **Performance:** Top-tier for local embeddings.
*   **Complexity:** Low.
*   **Cost:** Free (Local compute).
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** SentenceTransformers, OpenAI Embeddings.
*   **Integration points:** Chunk ingestion.
*   **Examples:** `TextEmbedding(model_name="BAAI/bge-small-en-v1.5")`
*   **Should Recall use it?** V2 (Excellent candidate to replace heavy PyTorch inference in workers).
## Part 3: Retrieval Models & Chunking Strategies

### 27. Voyage
*   **Purpose:** State-of-the-art embedding models as an API.
*   **How it works:** Specialized embedding models trained for specific domains (finance, law, code).
*   **Architecture:** Cloud API.
*   **Companies using it:** Harvey, Anthropic partners.
*   **Advantages:** Beats OpenAI/Cohere on MTEB benchmarks for specific domains.
*   **Disadvantages:** Cloud dependency, latency, cost.
*   **Maintenance burden:** Low.
*   **Performance:** High precision.
*   **Complexity:** Low.
*   **Cost:** Pay per token.
*   **License:** Proprietary.
*   **Open Source status:** Closed source.
*   **Alternatives:** OpenAI `text-embedding-3`, Cohere.
*   **Integration points:** Vector embedding pipeline.
*   **Examples:** `voyageai.Client().embed(texts)`
*   **Should Recall use it?** Maybe (If local MiniLM is proven insufficient).

### 28. Jina
*   **Purpose:** Open-source embedding models and infrastructure (Jina Embeddings v2).
*   **How it works:** 8k context window embedding models.
*   **Architecture:** Hosted API or local weights.
*   **Companies using it:** Open source community.
*   **Advantages:** Supports long context chunks (8192 tokens) natively.
*   **Disadvantages:** 8k chunks are usually bad for precise RAG anyway.
*   **Maintenance burden:** Low.
*   **Performance:** Good.
*   **Complexity:** Low.
*   **Cost:** Free (local).
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Nomic, BGE.
*   **Integration points:** Vector embedding.
*   **Examples:** `AutoModel.from_pretrained('jinaai/jina-embeddings-v2-base-en')`
*   **Should Recall use it?** Maybe.

### 29. BGE (BAAI)
*   **Purpose:** Top-tier open-source embedding models.
*   **How it works:** Trained by Beijing Academy of Artificial Intelligence; dominates MTEB leaderboards.
*   **Architecture:** HuggingFace / ONNX models.
*   **Companies using it:** Qdrant, Milvus, widespread open-source usage.
*   **Advantages:** Extremely high accuracy, small models available.
*   **Disadvantages:** None significant.
*   **Maintenance burden:** Low.
*   **Performance:** Excellent.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** MiniLM, Nomic.
*   **Integration points:** Embedding worker.
*   **Examples:** `BAAI/bge-large-en-v1.5`
*   **Should Recall use it?** V1/V2 (Strong candidate to replace MiniLM).

### 30. ColBERT
*   **Purpose:** Late interaction retrieval model.
*   **How it works:** Instead of a single vector per document, it computes a vector for *every token*. At search time, it computes the max similarity between query tokens and document tokens.
*   **Architecture:** Requires specialized vector DB support or dedicated engines (RAGatouille).
*   **Companies using it:** Stanford researchers, Vespa, advanced RAG setups.
*   **Advantages:** Phenomenal accuracy; solves the exact keyword matching issue that dense vectors struggle with.
*   **Disadvantages:** Massive storage overhead (10-50x larger than single vectors), slow retrieval if not optimized.
*   **Maintenance burden:** High.
*   **Performance:** High precision, slower latency.
*   **Complexity:** Very High.
*   **Cost:** Free (local).
*   **License:** MIT.
*   **Open Source status:** Open source.
*   **Alternatives:** Dense vectors + BM25 (Hybrid).
*   **Integration points:** Retrieval.
*   **Examples:** RAGatouille library.
*   **Should Recall use it?** Future (Storage costs in Postgres would explode; better to rely on pgvector + trigrams for now).

### 31. Nomic
*   **Purpose:** Long-context open-source embeddings (Nomic Embed).
*   **How it works:** Open weights, fully reproducible training data, 8192 context length.
*   **Architecture:** HuggingFace / Local.
*   **Companies using it:** Local AI ecosystem.
*   **Advantages:** Completely open data, long context.
*   **Disadvantages:** Newer, slightly less proven than BGE.
*   **Maintenance burden:** Low.
*   **Performance:** Good.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** Apache 2.0.
*   **Open Source status:** Fully Open source.
*   **Alternatives:** Jina.
*   **Integration points:** Embedding generation.
*   **Examples:** `nomic-ai/nomic-embed-text-v1.5`
*   **Should Recall use it?** Maybe.

### 32. Mixedbread
*   **Purpose:** Open-source embedding models and rerankers.
*   **How it works:** High quality reranker models (e.g., mxbai-rerank).
*   **Architecture:** Cross-encoder models.
*   **Companies using it:** Open source RAG builders.
*   **Advantages:** Tiny, fast rerankers that drastically improve RRF results.
*   **Disadvantages:** Requires CPU/GPU time during the search path.
*   **Maintenance burden:** Medium.
*   **Performance:** Fast for cross-encoders.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** Apache 2.0.
*   **Open Source status:** Open source.
*   **Alternatives:** Cohere Rerank, BGE Reranker.
*   **Integration points:** Search fusion layer.
*   **Examples:** `mixedbread-ai/mxbai-rerank-xsmall-v1`
*   **Should Recall use it?** V2 (Excellent option for our Reranker).

### 33. BM25
*   **Purpose:** Classic sparse keyword retrieval algorithm (TF-IDF evolution).
*   **How it works:** Scores documents based on exact keyword frequency and document length normalization.
*   **Architecture:** Standard full-text search.
*   **Companies using it:** Elasticsearch, PostgreSQL (partially), Solr.
*   **Advantages:** Unbeatable for exact name, ID, or rare word searches. No GPU required.
*   **Disadvantages:** Zero semantic understanding (fails on synonyms).
*   **Maintenance burden:** Low.
*   **Performance:** Ultra-fast.
*   **Complexity:** Low.
*   **Cost:** Free.
*   **License:** N/A (Algorithm).
*   **Open Source status:** N/A.
*   **Alternatives:** pg_trgm (fuzzy).
*   **Integration points:** Hybrid search.
*   **Examples:** Postgres `tsvector`.
*   **Should Recall use it?** V1 (We use `pg_trgm` which is adjacent and better for partial/fuzzy strings, but BM25 via Postgres `tsvector` should be evaluated).

### 34. Hybrid Retrieval
*   **Purpose:** Combining Dense (Vector) and Sparse (Keyword) search.
*   **How it works:** Runs both queries, merges results using Reciprocal Rank Fusion (RRF) or a convex combination.
*   **Architecture:** Search routing layer.
*   **Companies using it:** All modern RAG systems.
*   **Advantages:** Best of both worlds (semantics + exact match).
*   **Disadvantages:** Requires tuning the fusion weights.
*   **Maintenance burden:** Medium.
*   **Performance:** Slower (runs 2 queries).
*   **Complexity:** Medium.
*   **Cost:** N/A.
*   **License:** N/A.
*   **Open Source status:** N/A.
*   **Alternatives:** Pure vector.
*   **Integration points:** Search service.
*   **Examples:** `RRF = 1 / (k + rank_dense) + 1 / (k + rank_sparse)`
*   **Should Recall use it?** V1 (Currently implemented and mandated).

### 35. Recursive Retrieval
*   **Purpose:** Retrieving a small chunk for search precision, but passing a larger surrounding window to the LLM.
*   **How it works:** Search hits a 200-token chunk. The system recursively fetches the parent 1000-token document to provide context.
*   **Architecture:** Parent-child document mapping in DB.
*   **Companies using it:** Advanced LlamaIndex users.
*   **Advantages:** Highly precise search hits without sacrificing context for generation.
*   **Disadvantages:** Requires maintaining parent-child pointers in Postgres.
*   **Maintenance burden:** Medium.
*   **Performance:** Fast (requires 1 extra indexed DB lookup).
*   **Complexity:** Medium.
*   **Cost:** N/A.
*   **License:** N/A.
*   **Open Source status:** N/A.
*   **Alternatives:** Standard chunking.
*   **Integration points:** Chunking and Retrieval logic.
*   **Examples:** Fetch chunk `id=5`, then `SELECT * FROM chunks WHERE parent_id = (SELECT parent_id FROM chunks WHERE id=5)`.
*   **Should Recall use it?** V2.

### 36. Parent Retrieval
*   **Purpose:** (Synonymous with Recursive Retrieval in this context).
*   **Should Recall use it?** V2 (See 35).

### 37. Late Chunking
*   **Purpose:** Embedding generation technique (introduced by Jina).
*   **How it works:** Embeds the *entire* document through a transformer to share contextual attention, then averages the token embeddings for specific chunk boundaries.
*   **Architecture:** specialized embedding model support required.
*   **Companies using it:** Jina AI.
*   **Advantages:** Every chunk vector contains context about the whole document. Solves the "lost in the middle" chunking problem.
*   **Disadvantages:** Requires generating embeddings for massive token lengths at once (high VRAM usage).
*   **Maintenance burden:** Medium.
*   **Performance:** Slower embedding time.
*   **Complexity:** High.
*   **Cost:** Higher compute.
*   **License:** N/A.
*   **Open Source status:** N/A.
*   **Alternatives:** Standard chunking with metadata injection.
*   **Integration points:** Ingestion vectorization.
*   **Examples:** `jina-embeddings-v2` late chunking API.
*   **Should Recall use it?** Future.

### 38. Semantic Chunking
*   **Purpose:** Splitting documents at semantic boundaries rather than arbitrary character limits.
*   **How it works:** Embeds every sentence, calculates cosine similarity between adjacent sentences, and splits where similarity drops (indicating a topic change).
*   **Architecture:** Pre-processing step before main ingestion.
*   **Companies using it:** Custom RAG pipelines, LlamaIndex.
*   **Advantages:** Chunks represent complete thoughts; highly improves RAG.
*   **Disadvantages:** Extremely expensive (requires embedding every single sentence).
*   **Maintenance burden:** Medium.
*   **Performance:** Very slow ingestion.
*   **Complexity:** High.
*   **Cost:** High token usage.
*   **License:** N/A.
*   **Open Source status:** N/A.
*   **Alternatives:** Structural chunking (splitting by Markdown headers).
*   **Integration points:** Ingestion logic.
*   **Examples:** Greg Kamradt's semantic chunker.
*   **Should Recall use it?** Maybe (Structural chunking via Unstructured is cheaper and often better for formatted docs).

### 39. Adaptive Chunking
*   **Purpose:** Dynamically sizing chunks based on query needs.
*   **How it works:** Stores documents in a hierarchy (sentences -> paragraphs -> sections). The retriever decides which level of the hierarchy best answers the query.
*   **Architecture:** Graph or Tree based storage.
*   **Companies using it:** RAPTOR researchers.
*   **Advantages:** Optimal context size for any given query.
*   **Disadvantages:** Extremely complex to build and retrieve from SQL.
*   **Maintenance burden:** High.
*   **Performance:** Slower retrieval.
*   **Complexity:** Very High.
*   **Cost:** N/A.
*   **License:** N/A.
*   **Open Source status:** N/A.
*   **Alternatives:** Recursive Retrieval.
*   **Integration points:** Graph Database.
*   **Examples:** RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval).
*   **Should Recall use it?** Future (Wait for industry standardization).
