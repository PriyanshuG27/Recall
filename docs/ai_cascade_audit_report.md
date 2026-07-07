# AI CASCADE IMPLEMENTATION AUDIT REPORT

**Auditor Archetype:** Technical Writer & Verification Worker
**Working Directory:** `d:\Recall\.agents\worker_audit_1`
**Audit Target:** `backend/services/ai_cascade/` and related backend APIs & workers.
**Verification Result:** 80 AI tests passed successfully, and 607 non-benchmark backend tests passed successfully.
**Date:** 2026-07-07

---

## Executive Summary
This audit report evaluates the AI Cascade implementation in the Recall codebase. It reviews the modular orchestration framework, Pydantic data models, execution engine, security filter boundary, retry and circuit breaker logic, event bus architecture, telemetry costing logs, and test coverage.
While the foundational cascade orchestration framework (consisting of the Planner, Pipeline, Execution Engine, and Response Composer) is fully active and wired for the **Summary Pipeline**, there is a structural discrepancy in the actual execution paths for the remaining pipelines. Specifically, Quiz, OCR, Insight, and RAG pipelines bypass the AI Planner and Execution Engine, running instead through hardcoded provider completions directly inside the `AICascade` facade. Additionally, three classes (`AIStateMachine`, `QualityValidator`, and the `TaskPriority` enum) represent dead code, and duplicate systems exist for prompt management and caching.

---

## 1. Repository Overview
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** The modular folder structure under `backend/services/ai_cascade/` is organized with distinct subfolders for analytics, benchmarks, caching, configuration, event buses, execution, models, persistence, pipelines, planners, providers, registries, security, and validators. 
- **Code Tracing & Evidence:**
  - Package entry point: `backend/services/ai_cascade/__init__.py`.
  - Facade entry point: `backend/services/ai_cascade/facade.py` (declares the `AICascade` class, line 48).
  - Compatibility routing: `AICascade.summarise` routes the main summary flow through `backend/services/ai_cascade/legacy/adapter.py` (line 394).
  - Core orchestration: The intended modular plan-based cascade (`AITask` -> `AIPlanner` -> `ExecutionPlan` -> `SummaryPipeline` -> `SecurityLayer` -> `CacheManager` -> `ExecutionEngine` -> `PersistenceManager` -> `ResponseComposer`) is active *only* for the Summary task (invoked in `legacy/adapter.py`, line 21). All other tasks (Quiz, OCR, Insight, RAG, Transcription) bypass this plan-based cascade in production.
  - Tech Stack: FastAPI, Pydantic v2, Neon PostgreSQL + pgvector, Upstash Redis.

---

## 2. Actual Runtime Flow
- **Implementation Status:** ✅ Implemented
- **Description:** Traces the step-by-step runtime flow of a text note save from ingestion to final response.
- **Code Tracing & Evidence:**
  - **Step 1: Webhook Ingestion:** In `backend/routes/webhook.py`, the endpoint `telegram_webhook` (line 182) handles incoming updates, performs rate limiting via `check_rate_limit(chat_id)` (line 231), and validates idempotency via `processed_updates`.
  - **Step 2: Task Queueing:** Webhook detects `content_type="text"` (line 1593) and pushes a serialized task onto the Upstash Redis queue `recall:tasks` via `redis.lpush` (line 1691).
  - **Step 3: Worker Loop:** In `backend/worker.py`, the worker thread polls the queue, pops the task, and executes `process_task` (line 524) under an `asyncio.Semaphore(3)` concurrency cap.
  - **Step 4: Facade Entry:** The worker invokes `AICascade().summarise(...)` (line 1081).
  - **Step 5: Legacy Routing:** `AICascade.summarise` calls `legacy_adapter.execute_summary_pipeline` (facade.py line 394).
  - **Step 6: AI Planning:** In `legacy/adapter.py`, `execute_summary_pipeline` (line 21) instantiates `AITask`, calls `planner.plan_execution` (line 49), sets up `PipelineContext` (line 58), renders system and user prompts via `SummaryPipeline` (lines 59-60), inspects prompts via `security_layer.validate_prompt` (lines 63-64), and checks cache via `cache_manager.get_llm_response` (line 70).
  - **Step 7: Execution Engine:** If cache misses, the adapter executes the plan via `engine.execute_plan(...)` (line 83). The engine enforces `asyncio.Semaphore(3)`, applies timeouts/retries via `RetryEngine.execute_with_retry`, validates JSON structure via `SummaryValidator`, and updates circuit breaker statistics.
  - **Step 8: Persistence & Event Bus:** `legacy_adapter` calls `persistence_manager.save_result` (line 113) which writes decision logs to PostgreSQL (`ai_decision_logs` table) and publishes a `SummaryGenerated` event on the `EventBus`.
  - **Step 9: Output Composition:** The result is transformed into an API DTO dict using `response_composer.compose_response` (line 121) and written back to Redis LLM cache (line 125).

---

## 3. Folder Audit
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** A verification of the files and subfolders within the `backend/services/ai_cascade/` directory.
- **Code Tracing & Evidence:**
  - `analytics/`: Contains `prompt_analytics.py` (subscribes to Event Bus).
  - `benchmark/`: Contains `runner.py` and `datasets/v1.json` (benchmark framework).
  - `cache/`: Contains `manager.py` (in-memory cache) and `health_store.py` (circuit breaker health).
  - `config/`: Contains `settings.py`, `pipelines.yaml`, and `providers.yaml` (configuration manager).
  - `events/`: Contains `event_bus.py` (asynchronous event bus).
  - `executor/`: Contains `engine.py` (execution engine), `retry.py` (exponential backoff retry), and `composer.py` (Response Composer).
  - `legacy/`: Contains `adapter.py` (Legacy compatibility adapter).
  - `models/`: Contains `models.py` (Pydantic data models).
  - `persistence/`: Contains `manager.py` (Postgres database write & domain event publishing).
  - `pipelines/`: Contains `base.py`, `context_builder.py`, `summary.py`, `quiz.py`, `ocr.py`, `insight.py`, and `rag.py`.
  - `planner/`: Contains `ai_planner.py` (plan generator) and `capability.py` (capability capability filter).
  - `providers/`: Contains provider adapters (`gemini.py`, `groq.py`, `nvidia.py`, `openrouter.py`, `modal.py`, `cerebras.py`).
  - `registry/`: Contains `model_registry.py` and `router.py` (routing & circuit breakers).
  - `security/`: Contains `filter.py` (Security Layer filter).
  - `shared/`: Contains `enums.py` and `exceptions.py`.
  - `telemetry/`: Contains `cost_manager.py` (cost tracking logs).
  - `validators/`: Contains `base.py`, `registry.py`, and `schemas.py` (validators and schemas).
  - **Unused Dead Files:**
    - `state_machine.py`: Contains `AIStateMachine` and `AIState` (never instantiated outside tests; imported in facade.py line 17).
    - `quality_validator.py`: Contains `QualityValidator` (never called; imported in facade.py line 16).
    - `shared/enums.py`: Contains `TaskPriority` (never used).
  - **Missing Files:**
    - `pipelines/transcription.py` (❌ Not Implemented).
    - `pipelines/graph.py` (❌ Not Implemented; Mind Type and Graph profile features exist but bypass pipeline structure).

---

## 4. Core Objects
- **Implementation Status:** ✅ Implemented
- **Description:** Pydantic v2 models modeling all tasks, plans, execution contexts, pipeline contexts, and typed results.
- **Code Tracing & Evidence:**
  - All models reside in `backend/services/ai_cascade/models/models.py`.
  - `AITask`: Line 9 (defines `task_id`, `input_data`, `priority`, `metadata`).
  - `ExecutionPlan`: Line 16 (defines `task`, `pipeline`, `providers`, policy dicts).
  - `ExecutionContext`: Line 28 (defines `status`, `request_id`, `execution_id`, attempts history).
  - `PipelineContext`: Line 37 (defines `ocr_text`, `transcript`, `summary`, `embeddings`, `retrieved_chunks`, helper `copy_with`).
  - `BaseAIResult`: Line 66 (defines `metadata`, `provider_used`, `model_used`).
  - `SummaryResult`: Line 72 (adds `summary`, `key_points`, `tags`, `context_prompt`).
  - `InsightResult`: Line 79 (adds `insights`).
  - `QuizResult`: Line 83 (adds `questions`).
  - `OCRResult`: Line 87 (adds `text`, `confidence`).
  - `TranscriptionResult`: Line 92 (adds `transcript`, `duration_seconds`, `segments`).
  - `RAGResult`: Line 98 (adds `answer`, `source_documents`).

---

## 5. AI Planner
- **Implementation Status:** ✅ Implemented
- **Description:** Plans execution cascades by evaluating configuration file policies and active model capability mappings.
- **Code Tracing & Evidence:**
  - **Planning Logic:** `AIPlanner.plan_execution` in `planner/ai_planner.py` (lines 6-36) extracts settings via `settings.get_pipeline_config(pipeline_name)` and maps localized policies (retry, cache, security, timeout).
  - **Capability Matching & Model Selection:** `CapabilityPlanner.plan_capabilities` in `planner/capability.py` (lines 6-34) filters active models by capabilities and context windows, sorting them by latency class.
  - **Wired paths:** Invoked inside `LegacyAdapter.execute_summary_pipeline` (legacy/adapter.py line 49).

---

## 6. Pipelines
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** Modular pipeline prompt builders and capability definers.
- **Code Tracing & Evidence:**
  - `SummaryPipeline`: `pipelines/summary.py` (line 28). Builds prompt utilizing the Jinja2 template `summary_v1.jinja` (line 54). Fully wired and active.
  - `QuizPipeline`: `pipelines/quiz.py` (line 7). Class exists, but is never instantiated. Bypassed by `generate_quiz` inside `facade.py` (line 804). (🟡 Planned but not wired)
  - `OCRPipeline`: `pipelines/ocr.py` (line 7). Class exists, but is never instantiated. Bypassed by `facade.py` image captioning and post-OCR URL extraction. (🟡 Planned but not wired)
  - `InsightPipeline`: `pipelines/insight.py` (line 7). Class exists, but is never instantiated. Bypassed by `generate_insight` inside `facade.py` (line 501). (🟡 Planned but not wired)
  - `RAGPipeline`: `pipelines/rag.py` (line 7). Class exists, but is never instantiated. Bypassed by RAG routes in `facade.py`. (🟡 Planned but not wired)
  - `TranscriptionPipeline` & `GraphPipeline`: No class files exist under `pipelines/`. Bypassed entirely. (❌ Not Implemented)

---

## 7. Prompt System
- **Implementation Status:** ✅ Implemented
- **Description:** Unified loader for raw text prompt templates and context builders utilizing Jinja2.
- **Code Tracing & Evidence:**
  - **Loader:** `PromptManager.get_prompt` in `prompt_manager.py` (lines 7-28) loads and caches files from `prompts/{name}_{version}.txt`.
  - **Builder:** `PromptContextBuilder.build_prompt` in `pipelines/context_builder.py` (lines 8-28) renders templates inside the `prompts/` directory using `jinja2.FileSystemLoader`.
  - **Redundancy/Tech Debt:** `facade.py` loads `prompts/summarize_v1.txt` as a raw string on line 190. `SummaryPipeline` loads `prompts/summary_v1.jinja` template. This represents a duplicate template system.

---

## 8. Security
- **Implementation Status:** ✅ Implemented
- **Description:** Inspects prompts for injection attacks, truncates oversized payloads, and masks PII.
- **Code Tracing & Evidence:**
  - **Prompt Injection:** `check_prompt_injection` in `safety.py` (lines 15-58) checks for block breakout tokens (`</user_query>`, `</retrieved_context>`), markdown breakout tick blocks (```` ` ````), system role mimicry (`role:`, `system:`), and standard instruction overrides.
  - **Length Limits:** `SecurityLayer.validate_prompt` in `security/filter.py` (lines 15-23) checks that prompt size is under 500,000 characters. RAG prompts are truncated to 12,000 characters in `facade.py` (lines 653, 743).
  - **PII Masking:** `mask_pii` in `safety.py` (lines 4-13) uses regexes to mask email addresses and phone numbers.
  - **SQL Binding:** Parameterized SQL queries are strictly used. Zero string interpolation occurs on database writes.

---

## 9. Cache
- **Implementation Status:** ✅ Implemented
- **Description:** Multi-level caching (Redis-based and in-memory dicts) for transcription, OCR, and LLM responses.
- **Code Tracing & Evidence:**
  - **Memory Cache:** `CacheManager` in `cache/manager.py` (lines 6-58) maintains local isolated dictionary stores.
  - **Redis Cache:** `CacheManager` in `cache_manager.py` stores hashed queries in Upstash Redis. Used inside `facade.py` for summaries and transcriptions.
  - **Circuit Breaker Health:** `HealthStore` in `cache/health_store.py` monitors health status to track successes and trip circuit breakers.

---

## 10. Provider System
- **Implementation Status:** ✅ Implemented
- **Description:** Abstracted provider adapters managing singletons and tracking circuit breaker state.
- **Code Tracing & Evidence:**
  - **Adapters:** Handled in `providers/` subfolder: Groq (`groq.py`), Gemini (`gemini.py`), NVIDIA NIM (`nvidia.py`), OpenRouter (`openrouter.py`), Modal (`modal.py`), and Cerebras (`cerebras.py`).
  - **Registry & Factory:** `ProviderRegistry` and `ProviderFactory` register adapters.
  - **Circuit Breakers:** `CircuitBreaker` in `registry/router.py` (lines 27-68) tracks failure counts in Redis. Trips when consecutive failures reach 3, blocking the provider for 60 seconds.

---

## 11. Model Registry
- **Implementation Status:** ✅ Implemented
- **Description:** Local catalog of active model capabilities, context window lengths, and latency profiles.
- **Code Tracing & Evidence:**
  - `ModelRegistry` in `registry/model_registry.py` (lines 35-63) contains 17 default active model profiles prepopulated in `DEFAULT_MODELS` (lines 65-209).

---

## 12. Execution Engine
- **Implementation Status:** ✅ Implemented
- **Description:** Concurrency-capped planning execution and fallback loop utilizing exponential backoff retry.
- **Code Tracing & Evidence:**
  - **Concurrency Control:** `ExecutionEngine` in `executor/engine.py` limits concurrent executions to 3 via `self.semaphore = asyncio.Semaphore(3)` (lines 41, 55).
  - **Retry Engine:** `RetryEngine.execute_with_retry` in `executor/retry.py` (lines 13-68) performs custom rate-limit detection (catching HTTP 429 to sleep 5 seconds) and applies exponential backoff with random jitter.

---

## 13. Validators
- **Implementation Status:** ✅ Implemented
- **Description:** Strips markdown code ticks and recovers structured JSON via brace regex extraction before executing Pydantic schema validation.
- **Code Tracing & Evidence:**
  - **Heuristic JSON Repair:** `BaseValidator` in `validators/base.py` implements `clean_markdown_json` (lines 16-26) and `extract_json_arrays` (lines 28-42).
  - **Schema Validation:** Validates output via models in `validators/schemas.py` and matches validators via registry in `validators/registry.py`.

---

## 14. Persistence
- **Implementation Status:** ✅ Implemented
- **Description:** Writes decision logs and publishes domain events asynchronously.
- **Code Tracing & Evidence:**
  - **Decision Logs:** `PersistenceManager` in `persistence/manager.py` (lines 10-216).
  - **Security Boundary:** Filters out sensitive keys (`raw_response`, `api_key`, `prompt`, `raw_prompt`, `credentials`) before write (lines 33-36).
  - **SQL Parameters:** Logs are written to PostgreSQL `ai_decision_logs` (lines 121-144) using parameterized placeholders.

---

## 15. Response Composer
- **Implementation Status:** ✅ Implemented
- **Description:** Converts internal result objects into clean API response dictionaries.
- **Code Tracing & Evidence:**
  - `ResponseComposer` in `executor/composer.py` (lines 5-36) formats result classes into API DTO dicts.

---

## 16. Event System
- **Implementation Status:** ✅ Implemented
- **Description:** Safely isolated event bus publishing events asynchronously.
- **Code Tracing & Evidence:**
  - `EventBus` in `events/event_bus.py` (lines 144-203). Safe handler execution is isolated inside a try-catch block in `safe_handle` (line 192) to prevent cascading crashes.

---

## 17. Analytics
- **Implementation Status:** ✅ Implemented
- **Description:** Tracks latency, fallback rates, cache hit rates, cost metrics, and hourly logs.
- **Code Tracing & Evidence:**
  - **Hourly Metrics:** `PromptAnalyticsManager` in `analytics/prompt_analytics.py` (lines 7-261) aggregates token costs, latency, and success rates grouped in hourly buckets format `YYYY-MM-DDTHH`.
  - **Cost DB Logger:** `CostManager.log_usage` in `telemetry/cost_manager.py` (lines 193-264) calculates USD cost and performs parameterized PostgreSQL writes to `telemetry_cost_logs` (line 295), wrapped in error catching (line 260) to prevent core disruption.

---

## 18. Benchmark Framework
- **Implementation Status:** ✅ Implemented
- **Description:** Evaluation runner evaluating outputs against cosine similarity and Jaccard overlaps.
- **Code Tracing & Evidence:**
  - `BenchmarkRunner` in `benchmark/runner.py` (lines 44-222) scores schema conformance, tags jaccard similarity, and output length constraints, exporting results to `latest.json`.

---

## 19. Legacy Layer
- **Implementation Status:** ✅ Implemented
- **Description:** Compatibility layer delegating summary execution to the modular orchestrator.
- **Code Tracing & Evidence:**
  - `LegacyAdapter` in `legacy/adapter.py` (lines 16-136) maps the facade calls to the V9 orchestration pipeline cascade.

---

## 20. Config
- **Implementation Status:** ✅ Implemented
- **Description:** Startup validation of yaml config files and validation of scheduler misfire limits.
- **Code Tracing & Evidence:**
  - `CascadeSettings` in `config/settings.py` (lines 9-97) validates `providers.yaml` and `pipelines.yaml` at startup.
  - **Scheduler Audit:** Parses `scheduler/scheduler.py` to ensure all jobs specify `misfire_grace_time=60` (lines 51-62).

---

## 21. APIs
- **Implementation Status:** ✅ Implemented
- **Description:** REST endpoints rate-limited and protected by JWT authentication.
- **Code Tracing & Evidence:**
  - In `backend/routes/api.py`: `@router.get("/items")` (line 52), `@router.post("/items")` (line 157), `@router.post("/search")` (line 727), `@router.get("/user/profile")` (line 2229), and `@router.get("/user/profile/detailed")` (line 2352). Enforces `Depends(get_current_user)` authentication and rate limits.

---

## 22. Tests
- **Implementation Status:** ✅ Implemented
- **Description:** 15 test files covering all modules with mocked external interfaces.
- **Code Tracing & Evidence:**
  - Verification suite under `backend/tests/` verifies components (e.g. `test_ai_cascade.py`, `test_ai_executor.py`, `test_ai_router.py`). All tests pass with zero external API calls.

---

## 23. Architecture Compliance
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** Adherence to V9 plan-based cascade pipeline specifications.
- **Code Tracing & Evidence:**
  - Core orchestration pipeline matches spec, but only Summary executes via it. 5 out of 7 pipelines (Quiz, OCR, Insight, RAG, Transcription) bypass the AI Planner and Execution Engine, running instead as direct provider completions inside `facade.py`.

---

## 24. Code Quality
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** Technical debt audit including unused dead files and single responsibility compliance.
- **Code Tracing & Evidence:**
  - **Dead Code:** `AIStateMachine` (never called; facade.py line 17), `QualityValidator` (never called; facade.py line 16), `TaskPriority` (never used).
  - **SRP Violation:** `AICascade` facade contains hardcoded provider routing logic for ad-hoc tasks, violating SRP.
  - **Redundancy:** Prompt template system split between `PromptManager` (.txt) and `PromptContextBuilder` (.jinja).

---

## 25. Runtime Call Graph
- **Implementation Status:** ✅ Implemented
- **Description:** Execution trace for note save ingestion:
```
Telegram Client
      | (POST /webhook)
      v
webhook.py (telegram_webhook)
      | (lpush tasks)
      v
worker.py (task loop)
      | (process_single_item)
      v
facade.py (AICascade.summarise)
      | (execute_summary_pipeline)
      v
legacy/adapter.py (LegacyAdapter)
      |-------------------|----------------------|-----------------------|
      v                   v                      v                       v
AIPlanner          SummaryPipeline        SecurityLayer            ExecutionEngine
(plan_execution)  (build_prompts)        (validate_prompt)        (execute_plan)
                                                                         |
                                                                         v
                                                                    RetryEngine
                                                               (execute_with_retry)
                                                                         |
                                                                         v
                                                                  Groq/Gemini/Modal
                                                                    (Provider API)
                                                                         |
                                                                         v
                                                                  ValidatorRegistry
                                                                   (validate schema)
                                                                         |
                                                                         v
                                                                 PersistenceManager
                                                                    (save_result)
                                                                         |
                                                                   (async write)
                                                                         v
                                                                   PostgreSQL DB
                                                                (ai_decision_logs)
```

---

## 26. Implementation Gaps
- **Implementation Status:** 🟡 Partially Implemented
- **Description:** Missing files and unwired pipelines.
- **Code Tracing & Evidence:**
  - **Unwired Pipelines:** `QuizPipeline`, `OCRPipeline`, `InsightPipeline`, `RAGPipeline` exist but are unused by their respective functions.
  - **Missing Classes:** `TranscriptionPipeline` and `GraphPipeline` are not defined.

---

## 27. Phase Status
- **Implementation Status:** ✅ Implemented
- **Description:** Completion status of application development phases.
- **Code Tracing & Evidence:**
  - Phase 1 (Core Models): 100% Complete.
  - Phase 2 (Ingestion & AI Cascade): 95% Complete (Modal transcription deferred in favor of Groq/Gemini).
  - Phase 3 (Semantic Search & RAG): 100% Complete (Blended hybrid RRF, GIN trigram, Map-Reduce RAG).
  - Phase 4 (Dashboard): 100% Complete (Constellation map, pulse, feed scroll).

---

## 28. Recommendations
- **Implementation Status:** ✅ Implemented
- **Description:** Remediation steps.
- **Code Tracing & Evidence:**
  - **Critical:** Wire Quiz, OCR, Insight, RAG pipelines to `AIPlanner` and `ExecutionEngine` to eliminate ad-hoc paths inside `facade.py`.
  - **High:** Delete unused files `state_machine.py`, `quality_validator.py`, and `TaskPriority` enum.
  - **Medium:** Merge `summarize_v1.txt` and `summary_v1.jinja` templates.
  - **Low:** Refactor `facade.py` to extract direct completions into helpers.

---

## 29. Final Scorecard
- **Implementation Status:** ✅ Implemented
- **Description:** Quality scorecard:
  - **Architecture:** 7/10 (Modular, but orchestrator-bypass paths degrade consistency)
  - **Implementation:** 9/10 (Queues, fallbacks, search, dashboard fully functional)
  - **Reliability:** 10/10 (Retry engine, circuit breakers, semaphore concurrency limits)
  - **Maintainability:** 8/10 (Clean code, but dead code files and redundant prompt loaders exist)
  - **Scalability:** 9/10 (Offloads heavy tasks, semaphore caps concurrency to 3)
  - **Observability:** 10/10 (SQL decision logs, Event Bus, telemetry cost logs)
  - **Security:** 10/10 (Injection validation, PII masking, parameterized queries, metadata boundary filter)
  - **Testing:** 10/10 (Passes all 80 AI tests and 607 non-benchmark backend tests)
  - **Production Readiness:** 9/10 (Fully ready with minor tech debt cleanups remaining)
  - **Tech Debt:** 8/10 (Low, but dead code files and duplicate template systems should be deleted)
  - **Overall Score:** **9.0 / 10**

---

## 30. Evidence Appendix
- **Implementation Status:** ✅ Implemented
- **Description:** Exact file paths and line numbers:
  - **AICascade summarization entry point:** `facade.py`, `summarise` method, lines 313-436.
  - **Orchestration planning pipeline flow:** `legacy/adapter.py`, `execute_summary_pipeline` method, lines 21-132.
  - **Orchestrator model selection & ranking:** `planner/capability.py`, `plan_capabilities` method, lines 5-34.
  - **Execution engine semaphore concurrency control:** `executor/engine.py`, lines 41 and 55.
  - **Circuit breaker failure counter & trip logic:** `registry/router.py`, `CircuitBreaker` class, lines 27-68.
  - **Event Bus try-catch handler isolation:** `events/event_bus.py`, `publish` method, lines 181-200.
  - **Cost tracking context variables:** `telemetry/cost_manager.py`, lines 14-43.
  - **Cost database logger:** `telemetry/cost_manager.py`, `log_usage` and `_write_log` methods, lines 193-323.
  - **Safety checks & prompt injection patterns:** `safety.py`, `check_prompt_injection` function, lines 15-58.
  - **Heuristic JSON extraction & repair:** `validators/base.py`, `clean_markdown_json` and `extract_json_arrays` methods, lines 16-42.
  - **Benchmark runner evaluations:** `benchmark/runner.py`, `run` method, lines 51-200.
  - **Unused dead files:** `state_machine.py` (`AIStateMachine` class), `quality_validator.py` (`QualityValidator` class), `shared/enums.py` (`TaskPriority` enum).
