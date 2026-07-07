# Library Adoption Plan

This document turns the discussion into a practical adoption matrix.

## Decision rule
For every library, ask:
1. What problem does it solve?
2. Does Recall already solve this?
3. What does it replace?
4. Where does it fit?
5. How much code does it eliminate?
6. How much complexity does it add?
7. What are the tradeoffs?
8. Should Recall adopt it?
9. When should it be adopted?
10. Would building it ourselves be better?

---

## Document ingestion
### Unstructured
- Problem: parsing messy PDFs, DOCX, HTML, email, screenshots, and mixed documents.
- Recall today: partial support via custom parsing/OCR flows.
- Replaces: format-specific parsing glue.
- Fit: ingestion adapter layer.
- Adopt: yes.
- When: V1.2.
- Why not custom only: custom parsing is brittle across file types.

---

## Retrieval
### LlamaIndex
- Problem: recursive retrieval, parent-child retrieval, multi-vector retrieval, query engines.
- Recall today: hybrid search exists, but recursive/query composition is limited.
- Replaces: some retrieval orchestration.
- Fit: optional retrieval helper.
- Adopt: maybe.
- When: V2 if retrieval complexity grows.
- Why not core: it should not own Recall's architecture.

### Haystack
- Problem: modular retrieval pipelines.
- Recall today: custom retrieval already exists.
- Replaces: some orchestration code.
- Fit: retrieval pipeline helper.
- Adopt: maybe.
- When: V2 if modular pipeline composition becomes hard to maintain.
- Why not core: custom search already aligns well with Recall's stack.

### GraphRAG concepts
- Problem: graph/community based retrieval over knowledge neighborhoods.
- Recall today: graph ideas exist but are still lightweight.
- Replaces: purely chunk-based recall as the whole story.
- Fit: async graph projection and retrieval.
- Adopt: yes, as a direction.
- When: V2.
- Why not immediate: entity and relationship extraction need to mature first.

### DSPy
- Problem: prompt/program optimization against measured quality.
- Recall today: prompt system exists, but optimization is manual.
- Replaces: endless prompt tweaking by hand.
- Fit: extraction, query rewriting, answer synthesis.
- Adopt: yes.
- When: after eval sets exist, usually V2.
- Why not immediate: no metric set means no meaningful optimization target.

---

## Memory
### Mem0
- Problem: typed memory for semantic, episodic, and user memory.
- Recall today: items and notes exist, but memory policy is not formalized.
- Replaces: ad hoc memory heuristics.
- Fit: memory policy layer.
- Adopt: maybe.
- When: V2.
- Why not immediate: Recall should define memory semantics first.

### Zep / Letta
- Problem: memory management for AI systems.
- Recall today: not formalized.
- Replaces: custom memory helpers.
- Fit: optional memory infrastructure.
- Adopt: maybe.
- When: V2 or later.
- Why not immediate: can add complexity before memory policy is mature.

---

## Prompt / structured output
### Instructor
- Problem: schema-safe structured output and validation.
- Recall today: JSON repair exists in the cascade, but validation-first is better.
- Replaces: ad hoc output parsing.
- Fit: extraction and metadata normalization.
- Adopt: yes.
- When: V1.
- Why: low complexity and high value.

### Outlines
- Problem: constrained structured generation.
- Recall today: same area as Instructor.
- Replaces: brittle output parsing.
- Fit: extraction and structured generation.
- Adopt: maybe one of Instructor or Outlines, not both.
- When: V1.
- Why not both: overlapping responsibilities.

---

## Logging / observability
### Structlog
- Problem: structured logs.
- Recall today: logging exists but is inconsistent.
- Replaces: stringly-typed ad hoc logging.
- Fit: backend logging layer.
- Adopt: yes.
- When: V1.
- Why: small complexity increase, large maintainability gain.

### Sentry
- Problem: error monitoring and stack traces.
- Recall today: logging exists, but error visibility is not enough.
- Replaces: none; it complements logging.
- Fit: production error monitoring.
- Adopt: yes.
- When: V1.
- Why: essential for production debugging.

### OpenTelemetry
- Problem: distributed tracing.
- Recall today: not necessary for the first deployment.
- Replaces: nothing yet.
- Fit: future observability infrastructure.
- Adopt: later.
- When: V2/V3 if services multiply.
- Why not immediate: too much setup for too little current benefit.

---

## Storage / infra
### Qdrant
- Problem: dedicated vector database.
- Recall today: pgvector exists and is sufficient for now.
- Replaces: PostgreSQL vector storage only if scale demands it.
- Fit: future vector infrastructure.
- Adopt: maybe.
- When: V3 or only if pgvector becomes a bottleneck.
- Why not now: extra infra without proven need.

### Neo4j / graph DBs
- Problem: graph traversal and graph query performance.
- Recall today: graph semantics can still live in Postgres first.
- Replaces: some relational graph storage if needed.
- Fit: future graph backend.
- Adopt: maybe.
- When: V3 or only if graph queries become limiting.
- Why not now: graph usefulness is still more important than graph platform.

---

## Workflow / agents
### LangGraph
- Problem: durable, stateful workflows.
- Recall today: queue/worker model is enough.
- Replaces: custom workflows if they become complex.
- Fit: future orchestration.
- Adopt: maybe later.
- When: only when needed.
- Why not now: not a core requirement.

### CrewAI / AutoGen / Agno / CAMEL / Semantic Kernel / agent stacks
- Problem: agent orchestration and collaboration.
- Recall today: not the primary problem.
- Replaces: custom orchestration if the product becomes agent-heavy.
- Fit: future agent experiments.
- Adopt: no for core.
- When: only if a clearly defined agent use case appears.
- Why not now: Recall is a knowledge system first.

---

## Final recommendation
Adopt only the tools that remove real pain:
- V1: Unstructured, Structlog, Sentry, Instructor or Outlines
- V2: DSPy, GraphRAG concepts, optional memory helpers, optional retrieval helpers
- V3: infra migrations only if data proves the need

Do not adopt a library because it is popular. Adopt it because it removes an actual bottleneck.
