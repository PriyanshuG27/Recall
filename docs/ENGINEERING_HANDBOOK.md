# Recall Engineering Handbook

**The Official Source of Truth for the Recall Project**

Welcome to the Recall Engineering Handbook. This documentation is written at the standard of internal engineering documentation for tier-1 software companies. It is the absolute source of truth for the architecture, implementation, and operations of the Recall personal knowledge operating system.

Future developers, architects, and maintainers must rely entirely on these documents to understand how Recall works, why it was built this way, and what the constraints are. Every statement here is implementation-oriented.

## Core Architectural Principle
Recall owns the knowledge model. External libraries may help in narrow slots, but they do not define the product identity. The AI Cascade is FINAL. It is treated as a black box and must not be redesigned.

## Handbook Chapters

*   [Constitution: Project Principles](handbook/00_PROJECT_PRINCIPLES.md) ⭐
*   [Baseline: Current Recall Architecture](handbook/01_CURRENT_RECALL.md)
*   [Baseline: Architectural Weaknesses](handbook/02_PROBLEMS.md)
*   [Research: Technology Evaluation](handbook/03_RESEARCH.md)
*   [Research: Library Decisions](handbook/04_LIBRARY_DECISIONS.md)
*   [Target: Official Future Architecture](handbook/05_TARGET_ARCHITECTURE.md)
*   [Chapter 1: Core System Architecture & Concurrency Design](handbook/01_ARCHITECTURE_CONCURRENCY.md)
*   [Chapter 2: Ingestion, Normalization & Document Understanding](handbook/02_INGESTION_NORMALIZATION.md)
*   [Chapter 3: Hybrid Retrieval, Search & RAG Pipeline](handbook/03_RETRIEVAL_RAG.md)
*   [Chapter 4: Knowledge Graph, Semantic Hubs & Memory](handbook/04_GRAPH_MEMORY.md)
*   [Chapter 5: Security, Encryption & Privacy Layer](handbook/05_SECURITY_PRIVACY.md)
*   [Chapter 6: Logging & Production Observability](handbook/06_LOGGING_OBSERVABILITY.md)
*   [Chapter 7: Product Analytics & System Telemetry](handbook/07_ANALYTICS_TELEMETRY.md)
*   [Chapter 8: AI Cascade Orchestration Engine](handbook/08_AI_CASCADE_ENGINE.md)
*   [Operations: Production Runbook](handbook/06_PRODUCTION.md)

---
*Version 1.0.0 — Generated as the authoritative implementation guide.*

## Architecture Decision Records (ADRs)
* [001: Keep Postgresql](adrs/001-keep-postgresql.md)
* [002: Keep Fastapi](adrs/002-keep-fastapi.md)
* [003: Keep Ai Cascade](adrs/003-keep-ai-cascade.md)
* [004: Reject Langchain](adrs/004-reject-langchain.md)
* [005: Reject Llamaindex Architecture](adrs/005-reject-llamaindex-architecture.md)
* [006: Use Structlog](adrs/006-use-structlog.md)
* [007: Use Sentry](adrs/007-use-sentry.md)
* [008: Use Postgresql Analytics](adrs/008-use-postgresql-analytics.md)
* [009: Delay Neo4J](adrs/009-delay-neo4j.md)
* [010: Delay Qdrant](adrs/010-delay-qdrant.md)
* [011: Delay Dspy](adrs/011-delay-dspy.md)
* [012: Delay Langgraph](adrs/012-delay-langgraph.md)
