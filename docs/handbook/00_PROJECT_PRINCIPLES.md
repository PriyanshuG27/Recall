# Project Principles (00_PROJECT_PRINCIPLES)

**The Constitution of Recall**

This document outlines the philosophical bedrock of the Recall project. Every architectural decision, code contribution, and library adoption must be weighed against these principles. If a design violates this constitution, it must be rejected.

---

## 1. What Recall Is
Recall is an **AI-first personal knowledge operating system.** It is designed to act as a definitive "second brain." It ingests, understands, structures, and retrieves personal knowledge to augment human memory and reasoning. It is a long-term, durable utility.

## 2. What Recall Is Not
*   Recall is **not** an autonomous agent framework. It does not browse the web randomly or hallucinate actions on behalf of the user.
*   Recall is **not** a thin wrapper around a single AI provider (like a custom ChatGPT UI).
*   Recall is **not** a traditional file-storage system like Google Drive or Dropbox. It stores *knowledge*, not just files.

## 3. Design Philosophy
*   **Determinism over Magic:** The pathways of the system must be entirely predictable. The AI is used for reasoning and data extraction, not system orchestration.
*   **Data Durability:** A user's knowledge is their most valuable asset. Data loss, corruption, or unrecoverable states are the ultimate failure.
*   **Tenant Isolation:** Recall is multi-tenant by necessity, but isolated by design. Cross-tenant leakage is the ultimate security failure.

## 4. Library Philosophy
*   **Anti-Lock-In:** Avoid heavy, opinionated frameworks that abstract away core control flow (e.g., LangChain, LlamaIndex Orchestrators). 
*   **Embrace the Standard Library:** The Python standard library and raw SQL are vastly preferred over specialized pip packages for simple logic.
*   **Own the Core:** We rely on external APIs (Groq, Gemini) for raw compute, but we strictly own the orchestration, prompt generation, memory rules, and validation logic.

## 5. Security Philosophy
*   **Zero Trust AI:** LLMs are treated as adversarial inputs. All AI output must be validated, sanitized, and parsed strictly (via Pydantic) before touching the database.
*   **Encryption by Default:** All raw user knowledge is encrypted at rest (Fernet AES-128). If the database dumps, it should be useless to an attacker.
*   **Parameterization First:** Absolutely zero string interpolation in SQL or JSON parsing. 

## 6. AI Philosophy
*   **Models are Commodities:** The specific LLM used (Llama 3, Gemini, GPT-4) will constantly change. The AI Cascade engine must seamlessly hot-swap providers without breaking the app.
*   **Small Models for Ops, Large Models for Insight:** Use extremely fast, small, cheap models for background tasks (e.g., entity extraction, OCR cleanup). Reserve massive reasoning models (70B+) only for final RAG synthesis or complex user queries.
*   **Structured Outputs Only:** We do not rely on "vibe checks." All programmatic LLM calls must be forced into strict JSON outputs and validated.

## 7. Performance Philosophy
*   **Ingestion is Async, Retrieval is Sync:** Returning an HTTP 200 acknowledgment to a webhook must happen in <50ms. Complex parsing and embedding generation must happen asynchronously in the background.
*   **Protect the Accounts:** External APIs fail and rate limit. The worker queue must enforce strict concurrency caps (Semaphores) to ensure we never bankrupt the cloud account or get banned by providers.
*   **PostgreSQL is Fast Enough:** Do not adopt specialized NoSQL or Vector databases until we reach absolute limits. `pgvector` and standard B-trees are sufficient for V1.

## 8. Simplicity Philosophy
*   **Boring Infrastructure:** Vercel + Koyeb + Neon Postgres. Avoid Kubernetes, microservices, and Kafka until the monolith explicitly fails to scale.
*   **Consolidated State:** By keeping relational data, vectors, and graph edges in a single Postgres database, we eliminate split-brain data consistency issues and simplify backups.

## 9. When to Build vs. When to Adopt
*   **Build:** State management, prompt orchestration (AI Cascade), chunking rules, retrieval fusion (RRF), memory rules, and business logic.
*   **Adopt:** Deep foundational math and infrastructure (e.g., `pgvector` for HNSW, `unstructured` for parsing complex PDFs, `structlog` for JSON logging). If a problem requires a PhD to solve, adopt a library. If it requires domain knowledge of Recall, build it.

## 10. How Architectural Decisions Are Made
1.  Identify the architectural weakness in `02_PROBLEMS.md`.
2.  Review existing industry solutions in `03_RESEARCH.md`.
3.  Write an Architecture Decision Record (ADR) justifying the choice.
4.  If the decision is approved, it is documented in `05_TARGET_ARCHITECTURE.md` and implemented. No silent architectural shifts are permitted.
