# AI Cascade V9 Engineering Gap Analysis & Compliance Report

## Executive Summary
This report presents a comprehensive synthesis of the gap analysis of the AI Cascade V9 architecture implementation in the Recall backend (under `backend/services/ai_cascade/`) and its associated integration touchpoints across the codebase. 

While the foundational framework (consisting of the Planner, Pipeline, Execution Engine, and Response Composer) is fully wired for the **Summary Pipeline** (executed via the legacy adapter), there is a significant division between the new V9 execution pipeline and legacy facade layers. Crucially:
1. **Critical Pipeline Bypasses**: The majority of non-summary AI tasks (quizzes, insights, RAG, and OCR URL cleanup) completely bypass the `ExecutionEngine` and router. They are executed directly in `facade.py` using legacy helper methods, bypassing all circuit breakers, caches, telemetry database logging, PII masking, and prompt injection checks.
2. **Duplicated & Isolated Infrastructure**: Cache managers, circuit breakers, and security layers exist in duplicate forms (Redis-backed vs. in-memory only; regex-based validation vs. keyword-based safety). The summary pipeline uses an in-memory-only cache and a separate health store, making caching and health tracking isolated per-process and lost on restart.
3. **Analytics/Telemetry Logging Gaps**: Due to the separation of the execution engine and the router, LLM execution costs for the primary summary pipeline are never written to the `telemetry_cost_logs` database table. Furthermore, `PromptAnalyticsManager` stores metrics strictly in-memory globally, leading to complete data loss on process restart and leaking system-wide statistics to any authenticated user.
4. **Provider Exception Swallowing**: Providers swallow exceptions internally and return `None` (or log a warning), disabling the Retry Engine's specialized backoff logic (like sleeping on 429).
5. **Artificial Benchmarks**: The benchmark runner unconditionally mocks LLM provider completions using expected dataset values, masking real regressions.

---

## Component Status Index

| # | Component | Status | Primary File(s) / Path | Gaps Identified |
|---|---|---|---|---|
| 1 | AI Planner | 🟡 Partially Implemented | `planner/ai_planner.py` | Uses static configuration lookups, bypassing dynamic capability planning. |
| 2 | Execution Plan | 🟡 Partially Implemented | `models/models.py` | Runtime execution plans use hardcoded provider-to-model mappings. |
| 3 | Capability Planner | ⚠️ Planned but not wired | `planner/capability.py` | Exists in codebase but is never instantiated, called, or wired. |
| 4 | Provider Manager | 🟡 Partially Implemented | `providers/manager.py` | Decoupled circuit-breaker states from router health checks. |
| 5 | Provider Factory | 🟡 Partially Implemented | `providers/factory.py` | Bypassed by static instantiations in router, creating duplicate instances. |
| 6 | Execution Engine | 🟡 Partially Implemented | `executor/engine.py` | Bypassed by all non-summary tasks; fails to log cost database telemetry. |
| 7 | Retry Engine | 🟡 Partially Implemented | `executor/retry.py` | Disabled for specialized exceptions due to provider exception swallowing. |
| 8 | Validators | 🟡 Partially Implemented | `validators/schemas.py` | Incompatible schemas for Quiz/Insight/RAG; re-parsing bypasses repairs. |
| 9 | Pipelines | 🟡 Partially Implemented | `pipelines/` | Quiz/Insight/RAG/OCR pipelines are unwired; Transcription/Graph are missing. |
| 10 | Prompt System | 🟡 Partially Implemented | `prompt_manager.py` | Dual text vs. Jinja loading paths; production runs basic summaries. |
| 11 | Cache | 🟡 Partially Implemented | `cache/manager.py` | Summaries cached in local process memory instead of Upstash Redis. |
| 12 | Security | 🟡 Partially Implemented | `security/filter.py` | Split implementations (regex vs. keyword safety); bypassed on facade routes. |
| 13 | Persistence | 🟡 Partially Implemented | `persistence/manager.py` | Decision logs omitted for all non-summary tasks. |
| 14 | Event Bus | 🟡 Partially Implemented | `events/event_bus.py` | No events published for bypassed non-summary tasks. |
| 15 | Analytics | 🟡 Partially Implemented | `analytics/` | Metrics stored in-memory globally; data leak of global metrics to users. |
| 16 | Benchmark | 🟡 Partially Implemented | `benchmark/runner.py` | Unconditional LLM mocking; missing try/finally block in database scripts. |
| 17 | Configuration | 🟡 Partially Implemented | `config/` | Non-summary pipeline parameters in configurations are ignored. |
| 18 | Models | 🟡 Partially Implemented | `models/models.py` | Bypassed by hardcoded execution engine mappings and ad-hoc string outputs. |
| 19 | Providers | 🟡 Partially Implemented | `providers/` | Swallows all exceptions internally; defaults to non-existent model IDs. |
| 20 | Folder Structure | 🟡 Partially Implemented | N/A | Script file in `.agents/` metadata directory; split script folders. |
| 21 | API Layer | 🟡 Partially Implemented | `routes/api.py` | Inefficient facade instantiation; duplicate websocket routes. |
| 22 | Worker | ✅ Implemented | `worker.py` | Fully functional, but instantiates facade locally on each task. |
| 23 | Legacy Adapter | 🟡 Partially Implemented | `legacy/adapter.py` | Re-parses raw completions via `json.loads`, discarding repaired JSON. |
| 24 | Dead Code Detection | 🗑 Dead Code | Various | Orphaned classes, unused script files, and unrendered frontend pages. |
| 25 | Architecture Violations | 🟡 Partially Implemented | Various | Unauthenticated Telegram webhook route; global telemetry leak. |
| 26 | Missing V9 Features | 🟡 Partially Implemented | N/A | Missing core pipelines (Transcription, Graph); duplicate websockets. |

---

## Detailed Gap Findings

### 1. AI Planner
* **Title**: AI Planner Relies on Static YAML Configuration and Bypasses Capability Planner
* **Severity**: Medium
* **Evidence**:
  In `backend/services/ai_cascade/planner/ai_planner.py` (lines 20-30):
  ```python
  providers = pipe_cfg.get("providers", [])
  ...
  return ExecutionPlan(
      task=task,
      pipeline=pipeline_name,
      providers=providers,
      ...
  )
  ```
* **Exact File**: `backend/services/ai_cascade/planner/ai_planner.py`
* **Exact Function**: `AIPlanner.plan_execution`
* **Exact Line Numbers**: 15-36
* **Runtime Impact**: The planning phase is statically bound to lists in `pipelines.yaml` instead of dynamically evaluating model attributes, latency profiles, or registered capabilities, rendering the catalog static and unresponsive to live changes.
* **Root Cause**: Capability sorting and ranking was not integrated into the planner execution flow.
* **Suggested Fix**: Refactor `AIPlanner` to load registered capabilities and route target provider selection through `CapabilityPlanner` ranking logic.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: Capability Planner, Model Registry

---

### 2. Execution Plan
* **Title**: Execution Plan Models Overridden by Hardcoded Mapper in Execution Engine
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/executor/engine.py` (lines 61-75):
  ```python
  default_models = {
      "groq": "openai/gpt-oss-120b",
      "nvidia": "qwen/qwen3-next-80b-a3b",
      "cerebras": "cerebras/openai/gpt-oss-120b",
      ...
  }
  model_id = default_models.get(provider_name.lower(), "default-model")
  ```
* **Exact File**: `backend/services/ai_cascade/executor/engine.py`
* **Exact Function**: `ExecutionEngine.execute_plan`
* **Exact Line Numbers**: 61-89
* **Runtime Impact**: Execution plans generated by the planner containing model configurations are overridden during engine execution. This prevents the execution of custom target models specified in the plan.
* **Root Cause**: Temporary hardcoded fallback map left in place instead of parsing execution plan model metadata.
* **Suggested Fix**: Update `execute_plan` to inspect the `ExecutionPlan` or `AITask` metadata for target model identifiers instead of using a static dictionary fallback.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: AI Planner, Models

---

### 3. Capability Planner
* **Title**: Capability Planner Class is Fully Unwired and Bypassed
* **Severity**: High
* **Evidence**:
  The file `backend/services/ai_cascade/planner/capability.py` contains `CapabilityPlanner` but is never imported or instantiated in `ai_planner.py`, `engine.py`, or `facade.py`.
* **Exact File**: `backend/services/ai_cascade/planner/capability.py`
* **Exact Function**: N/A
* **Exact Line Numbers**: Entire file
* **Runtime Impact**: Model registry capabilities, cost thresholds, and context window sorting cannot be evaluated dynamically at runtime, reducing the system's ability to automatically failover to smaller/cheaper models.
* **Root Cause**: Left in an unwired state during the planning module integration phase.
* **Suggested Fix**: Instantiate `CapabilityPlanner` inside `AIPlanner` and call its model ranking methods during the planning step.
* **Estimated Effort**: Medium
* **Risk Level**: Medium
* **Dependencies**: AI Planner, Model Registry

---

### 4. Provider Manager
* **Title**: Health States and Circuit Breakers Isolated Between Router and Provider Manager
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/registry/router.py` (lines 27-35):
  ```python
  class CircuitBreaker:
      def _key_fail(self, provider: str) -> str:
          return f"ai_breaker:fail_count:{provider}"
  ```
  In `backend/services/ai_cascade/cache/health_store.py` (lines 6-15):
  ```python
  class HealthStore:
      def _consecutive_failures_key(self, provider: str) -> str:
          return f"ai_cascade:health:{provider.lower()}:consecutive_failures"
  ```
* **Exact File**: `backend/services/ai_cascade/registry/router.py` & `backend/services/ai_cascade/cache/health_store.py`
* **Exact Function**: `CircuitBreaker` vs. `HealthStore`
* **Exact Line Numbers**: `router.py:27-68` and `health_store.py:6-70`
* **Runtime Impact**: A provider marked unhealthy by ad-hoc router operations (e.g. voice transcription) remains active and continues to be called by the `ExecutionEngine` summary pipeline. This leads to duplicate timeouts, latency spikes, and inconsistent failover behaviors.
* **Root Cause**: Independent, decoupled circuit breaker implementations using different Redis keys.
* **Suggested Fix**: Refactor `AIRouter` to delegate provider health checks and failure reporting to the unified `health_store` and `provider_manager` singleton. Delete the duplicate `CircuitBreaker` class.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: Redis Cache

---

### 5. Provider Factory
* **Title**: Duplicate Provider Adapter Instances Created via Static Instantiation in Router
* **Severity**: Medium
* **Evidence**:
  In `backend/services/ai_cascade/registry/router.py` (lines 72-80):
  ```python
  adapters = {
      "groq": GroqProvider(),
      "gemini": GeminiProvider(),
      "openrouter": OpenRouterProvider(),
      ...
  }
  ```
  In `backend/services/ai_cascade/providers/factory.py` (lines 6-17):
  ```python
  class ProviderFactory:
      def get_provider(self, provider_name: str) -> BaseProvider:
          ...
          self._instances[name_lower] = provider_cls()
  ```
* **Exact File**: `backend/services/ai_cascade/registry/router.py` & `backend/services/ai_cascade/providers/factory.py`
* **Exact Function**: `AIRouter.adapters` vs. `ProviderFactory.get_provider`
* **Exact Line Numbers**: `router.py:72-80` and `factory.py:6-17`
* **Runtime Impact**: Multiple independent instances of provider client classes are instantiated in memory. This duplicates HTTP client connection references and bypasses factory lifespan hook management.
* **Root Cause**: `AIRouter` instantiates all providers statically at import time rather than utilizing the factory.
* **Suggested Fix**: Modify `AIRouter` to retrieve adapter instances dynamically using `provider_factory.get_provider(provider_name)`.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: Provider Factory

---

### 6. Execution Engine
* **Title**: Execution Engine Bypassed for Quiz, Insight, RAG, and OCR Tasks
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/facade.py` (lines 521-537, 821-836, 674-697):
  ```python
  # generate_insight direct routing:
  if provider == "groq" and settings.GROQ_API_KEY:
      res = await self._call_groq_llm(messages, temperature=0.3, timeout=15.0)
  ```
* **Exact File**: `backend/services/ai_cascade/facade.py`
* **Exact Function**: `AICascade.generate_insight`, `AICascade.generate_quiz`, `AICascade.answer_question`, `AICascade.extract_clean_urls_and_meta`
* **Exact Line Numbers**: 521-537, 674-697, 821-836, 925-938
* **Runtime Impact**: The core execution engine is bypassed for the majority of non-summary AI tasks. This prevents unified planning, health monitoring, exception-handling retries, and cost telemetry tracking.
* **Root Cause**: Ad-hoc development was used to implement helper functions inside the facade without integrating the execution engine pipeline.
* **Suggested Fix**: Refactor all non-summary facade methods to delegate execution through the `ExecutionEngine` by passing a structured `AITask`.
* **Estimated Effort**: High
* **Risk Level**: Medium
* **Dependencies**: Pipelines, AI Planner

---

### 7. Retry Engine
* **Title**: Provider Exception Swallowing Disables Specialized Retry and Rate-Limit Backoff
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/providers/groq.py` (lines 95-97):
  ```python
  except Exception as e:
      logger.warning("Groq call failed for model %s with exception: %s", current_model, e)
      continue
  ```
  In `backend/services/ai_cascade/executor/retry.py` (lines 38-42):
  ```python
  except (CascadeTimeoutError, ProviderError) as exc:
      ...
      is_rate_limit = isinstance(exc, RateLimitExceededError)
  ```
* **Exact File**: `backend/services/ai_cascade/providers/groq.py` (also affects `gemini.py`, `nvidia.py`, `openrouter.py`, `cerebras.py`, `modal.py`)
* **Exact Function**: `GroqProvider.chat_completion`, `GeminiProvider.chat_completion`, etc.
* **Exact Line Numbers**: `groq.py:74-97`, `gemini.py:61-87`, `nvidia.py:43-53`
* **Runtime Impact**: The `RetryEngine` never catches specialized exceptions like `RateLimitExceededError` or `CascadeTimeoutError`. Consequently, the system uses generic exponential backoff instead of executing specialized behaviors like sleeping for 5 seconds on HTTP 429.
* **Root Cause**: Provider adapters catch all exceptions internally and return `None` rather than raising them.
* **Suggested Fix**: Refactor providers to raise appropriate custom exceptions (`RateLimitExceededError`, `CascadeTimeoutError`, `ProviderError`) instead of swallowing them.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: Retry Engine

---

### 8. Validators
* **Title**: Structural Incompatibility between Quiz, Insight, RAG Validators and Runtime Outputs
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/validators/schemas.py` (lines 16-23):
  ```python
  class QuizQuestionModel(BaseModel):
      question: str = Field(..., min_length=5)
      options: List[str] = Field(..., min_length=2)
      answer_index: int
  ```
  In `backend/services/ai_cascade/facade.py` (lines 806-812), the endpoint returns `correct_index` instead of `answer_index`.
* **Exact File**: `backend/services/ai_cascade/validators/schemas.py` & `backend/services/ai_cascade/facade.py`
* **Exact Function**: `AICascade.generate_quiz`, `AICascade.generate_insight`, `AICascade.answer_question`
* **Exact Line Numbers**: `schemas.py:11-34` and `facade.py:804-843`
* **Runtime Impact**: Wiring these tasks directly to the modular `ExecutionEngine` will immediately trigger validation exceptions, crashing requests due to schema mismatches.
* **Root Cause**: Validators were developed independently of the active facade runtime contracts and test suite expectations.
* **Suggested Fix**: Align schemas in `schemas.py` with the actual runtime requirements expected by the frontend and unit tests (e.g. rename `answer_index` to `correct_index`, support raw text fallback fields).
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 9. Pipelines
* **Title**: Quiz, OCR, Insight, and RAG Pipelines Unwired and Bypassed; Transcription and Graph Missing
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/pipelines/`: `quiz.py`, `ocr.py`, `insight.py`, and `rag.py` exist but are never instantiated or called. Additionally, `TranscriptionPipeline` and `GraphPipeline` are not defined.
* **Exact File**: `backend/services/ai_cascade/pipelines/`
* **Exact Function**: N/A
* **Exact Line Numbers**: N/A
* **Runtime Impact**: Non-summary tasks bypass unified execution pipeline controls (caches, validators, events, analytics).
* **Root Cause**: Incomplete modular pipeline implementation cycle.
* **Suggested Fix**: Implement missing pipeline classes and configure `LegacyAdapter` to delegate non-summary tasks to their corresponding pipeline instances.
* **Estimated Effort**: High
* **Risk Level**: Medium
* **Dependencies**: Execution Engine

---

### 10. Prompt System
* **Title**: Split Prompt Loading Implementations (Txt vs. Jinja2) and Production Summary Template Mismatch
* **Severity**: Medium
* **Evidence**:
  In `backend/services/ai_cascade/prompt_manager.py` (lines 7-28):
  ```python
  file_path = os.path.join(dir_path, "prompts", f"{name}_{version}.txt")
  ```
  In `backend/services/ai_cascade/pipelines/context_builder.py` (lines 8-29):
  ```python
  self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)))
  ```
  Also, production summaries use `summary_v1.jinja` which lacks formatting rules present in `summarize_v1.txt`.
* **Exact File**: `backend/services/ai_cascade/prompt_manager.py` & `backend/services/ai_cascade/pipelines/context_builder.py`
* **Exact Function**: `PromptManager.get_prompt` vs. `PromptContextBuilder.build_prompt`
* **Exact Line Numbers**: `prompt_manager.py:7-28` and `context_builder.py:8-29`
* **Runtime Impact**: Inconsistent formatting, dual loading paths, and degradation of summary quality because advanced guidelines from `summarize_v1.txt` are omitted in production.
* **Root Cause**: Split evolution of legacy text prompts and the new Jinja context builder.
* **Suggested Fix**: Consolidate prompt rendering under `PromptContextBuilder`, convert all plain text prompts to `.jinja` templates, and merge formatting rules into `summary_v1.jinja`.
* **Estimated Effort**: Low-Medium
* **Risk Level**: Low
* **Dependencies**: Jinja2

---

### 11. Cache
* **Title**: Duplicate Caching Managers Cause Summary Cache Isolation in Local Process Memory
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/legacy/adapter.py` (line 8):
  ```python
  from backend.services.ai_cascade.cache import cache_manager
  ```
  This imports the in-memory `cache_manager` from `cache/manager.py` instead of the Redis-backed one in `cache_manager.py`.
* **Exact File**: `backend/services/ai_cascade/legacy/adapter.py`
* **Exact Function**: `LegacyAdapter.execute_summary_pipeline`
* **Exact Line Numbers**: 8, 70
* **Runtime Impact**: Cached summaries are isolated to process memory space. Since web servers and workers run in different processes, cache hits are extremely low, and entries are completely lost on restart, violating V9 Redis caching specifications.
* **Root Cause**: Incorrect import targets during the caching integration stage.
* **Suggested Fix**: Update imports in `legacy/adapter.py` to use the Redis-backed `CacheManager` imported from `backend.services.ai_cascade.cache_manager`.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: Redis Client

---

### 12. Security
* **Title**: Inconsistent Validation and Bypassed Safety Checks on Multiple Facade Routes
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/safety.py` (PII masking and override keywords) vs. `backend/services/ai_cascade/security/filter.py` (regex matches and 500k character limits). Endpoint functions like `generate_quiz` and `generate_insight` bypass safety validation entirely.
* **Exact File**: `backend/services/ai_cascade/safety.py` & `backend/services/ai_cascade/security/filter.py`
* **Exact Function**: `check_prompt_injection` vs. `SecurityLayer.validate_prompt`
* **Exact Line Numbers**: `safety.py:15-58` and `filter.py:5-26`
* **Runtime Impact**: Inconsistent exploit protection. Bypassed routes are vulnerable to injection attacks, and the new pipeline lacks length restrictions and keywords validation present in the safety module.
* **Root Cause**: Redundant and split safety validation implementations.
* **Suggested Fix**: Merge security rules into a unified `SecurityLayer` and apply it to all incoming AI tasks.
* **Estimated Effort**: Low-Medium
* **Risk Level**: Low
* **Dependencies**: None

---

### 13. Persistence
* **Title**: Decision Logging Bypassed for Non-Summary Tasks
* **Severity**: High
* **Evidence**:
  `PersistenceManager.save_result` is only called inside `legacy/adapter.py`. The other tasks (quiz, insight, RAG, etc.) execute directly inside `facade.py` and never invoke the persistence manager.
* **Exact File**: `backend/services/ai_cascade/persistence/manager.py`
* **Exact Function**: `PersistenceManager.save_result`
* **Exact Line Numbers**: 10-51
* **Runtime Impact**: No AI decision logs are written to the database table `ai_decision_logs` for any task except summaries, causing a complete lack of system auditability for other AI features.
* **Root Cause**: Bypassed facade routes do not execute the modular pipeline.
* **Suggested Fix**: Refactor all non-summary tasks to route through the `ExecutionEngine` which automatically triggers persistence.
* **Estimated Effort**: High (requires refactoring facade endpoints)
* **Risk Level**: Medium
* **Dependencies**: Execution Engine

---

### 14. Event Bus
* **Title**: Event Publishing Bypassed for Non-Summary Tasks
* **Severity**: Medium
* **Evidence**:
  `facade.py` methods do not publish any events (such as `LLMRequestStarted`, `LLMRequestFinished`, `ExecutionSucceeded`, or `ExecutionFailed`) to the event bus.
* **Exact File**: `backend/services/ai_cascade/events/event_bus.py`
* **Exact Function**: N/A
* **Exact Line Numbers**: N/A
* **Runtime Impact**: Downstream event subscribers and telemetry collectors receive zero data regarding quiz, insight, or RAG execution status.
* **Root Cause**: Facade routes bypass the event-publishing execution engine.
* **Suggested Fix**: Route these tasks through the `ExecutionEngine` to restore event-driven monitoring.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: Event Bus

---

### 15. Analytics
* **Title**: Transient In-Memory Analytics and Missing Telemetry Cost Database Logging
* **Severity**: High
* **Evidence**:
  `PromptAnalyticsManager` (in `analytics/prompt_analytics.py`) initializes stats strictly in-memory (lines 8-14). Also, `engine.py` estimates tokens and publishes events but never writes to `telemetry_cost_logs` via `CostManager.log_usage`.
* **Exact File**: `backend/services/ai_cascade/analytics/prompt_analytics.py` & `backend/services/ai_cascade/executor/engine.py`
* **Exact Function**: `PromptAnalyticsManager.__init__` & `ExecutionEngine.execute_plan`
* **Exact Line Numbers**: `prompt_analytics.py:8-14` and `engine.py:130-181`
* **Runtime Impact**: Aggregated analytics metrics are process-isolated and lost entirely on restart. Additionally, summary generation costs (the main LLM load) are completely missing from the `telemetry_cost_logs` database table.
* **Root Cause**: Missing database log handler for the execution engine, and lack of backing store (like Upstash Redis) for metrics.
* **Suggested Fix**: Register an event handler for `LLMRequestFinished` to write costs using `CostManager.log_usage`, and refactor `PromptAnalyticsManager` to store aggregated metrics in Redis.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: Redis Client, Cost Manager

---

### 16. Benchmark
* **Title**: Benchmark Runner Bypasses Real AI Execution via Unconditional Mocking
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/benchmark/runner.py` (lines 71-92):
  ```python
  # Patch all provider completions to return mock JSON response
  async def mock_comp(*args, **kwargs):
      return mock_json_str
  
  GroqProvider.chat_completion = mock_comp
  GeminiProvider.chat_completion = mock_comp
  ```
* **Exact File**: `backend/services/ai_cascade/benchmark/runner.py`
* **Exact Function**: `run`
* **Exact Line Numbers**: 71-92
* **Runtime Impact**: The benchmark runner always records 100% or near-perfect evaluation scores because it feeds expected answers directly back to the mock wrapper. Real model quality regressions, parsing bugs, or API latencies are completely hidden.
* **Root Cause**: LLM provider completions are unconditionally mocked inside the benchmark loop.
* **Suggested Fix**: Introduce a toggle (`BENCHMARK_MOCK=False`) to run real LLM completions against the dataset for evaluation.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 17. Configuration
* **Title**: Configured Pipeline Parameters Ignored for Non-Summary Tasks
* **Severity**: Low
* **Evidence**:
  `pipelines.yaml` lists configurations for `rag`, `quiz`, `ocr`, and `insight` (timeouts, cache settings, provider lists), but these values are never read by the legacy functions in `facade.py` which hardcode their timeouts and providers.
* **Exact File**: `backend/services/ai_cascade/config/pipelines.yaml`
* **Exact Function**: N/A
* **Exact Line Numbers**: N/A
* **Runtime Impact**: Changes to timeouts or provider priorities in configuration files are ignored for non-summary pipelines, requiring codebase updates to apply modifications.
* **Root Cause**: Non-summary routes bypass the configuration-driven execution engine.
* **Suggested Fix**: Refactor facade methods to delegate execution through the `ExecutionEngine`.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: CascadeSettings

---

### 18. Models
* **Status**: 🟡 Partially Implemented
* **Title**: Models Bypassed by Ad-hoc Facade Strings and Hardcoded Engine Mappings
* **Severity**: Medium
* **Evidence**:
  `models.py` defines schemas like `RAGResult` and `InsightResult`, but facade routes return raw string outputs directly, bypassing structured models.
* **Exact File**: `backend/services/ai_cascade/models/models.py`
* **Exact Function**: N/A
* **Exact Line Numbers**: 79-102
* **Runtime Impact**: Inconsistent schema validation and data integrity issues if client layers expect structured JSON properties but receive raw text strings.
* **Root Cause**: Facade methods return raw LLM outputs directly instead of parsing them into structured dataclasses.
* **Suggested Fix**: Parse facade outputs into their corresponding result models before returning them to callers.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: None

---

### 19. Providers
* **Title**: Provider Exceptions Swallowed Internally and Defaulting to Hardcoded Fake Models
* **Severity**: High
* **Evidence**:
  In `backend/services/ai_cascade/providers/groq.py` (lines 95-97):
  ```python
  except Exception as e:
      logger.warning("Groq call failed for model %s with exception: %s", current_model, e)
      continue
  ```
  Also, multiple provider classes fall back to fake models like `openai/gpt-oss-120b`.
* **Exact File**: `backend/services/ai_cascade/providers/groq.py` (and cerebras.py, openrouter.py)
* **Exact Function**: `GroqProvider.chat_completion`, `CerebrasProvider.chat_completion`, etc.
* **Exact Line Numbers**: `groq.py:74-97`, `cerebras.py:38`, `openrouter.py:36`
* **Runtime Impact**: Swallowed exceptions disable specialized rate-limiting retries. Additionally, defaulting to fake placeholder models results in immediate remote provider API failures.
* **Root Cause**: Temporary placeholders left in default settings, and generic exception swallowing.
* **Suggested Fix**: Refactor providers to raise appropriate exceptions, and set defaults to valid, active model IDs (e.g. `llama-3.3-70b-versatile` for Groq).
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 20. Folder Structure
* **Title**: Source Script inside `.agents/` Metadata Directory and Duplicate Scripts Folders
* **Severity**: Low
* **Evidence**:
  File `backend/services/ocr_worker.py` and `.agents/auditor_audit_1/verify_report.py` violate layout compliance rules. Also, split script folders exist at `scripts/` (root) and `backend/scripts/`.
* **Exact File**: `.agents/auditor_audit_1/verify_report.py` & `backend/services/ocr_worker.py`
* **Exact Function**: N/A
* **Exact Line Numbers**: Entire files
* **Runtime Impact**: Violates project layout compliance (no executable code inside `.agents/`). Duplicated scripts directories increase developer overhead and complicate script execution paths.
* **Root Cause**: Leftover files from previous audits and split script setups.
* **Suggested Fix**: Delete `.agents/auditor_audit_1/verify_report.py` and merge all utility scripts under a unified root directory.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 21. API Layer
* **Title**: Inefficient Local Instantiation of `AICascade` in Route Handlers
* **Severity**: Medium
* **Evidence**:
  In `backend/routes/api.py` (lines 213, 355, 471, etc.):
  ```python
  from backend.services.ai_cascade import AICascade
  cascade = AICascade()
  ```
  Repeated inside route functions.
* **Exact File**: `backend/routes/api.py`
* **Exact Function**: Various route handlers
* **Exact Line Numbers**: Multiple (e.g. 213, 355, 471)
* **Runtime Impact**: Inefficient allocation and garbage collection of `AICascade` instances on every HTTP request, and inability to maintain shared state.
* **Root Cause**: Routes instantiate the class locally instead of importing a shared singleton instance.
* **Suggested Fix**: Export a central singleton instance of `AICascade` from `__init__.py` and use it throughout all routes.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 22. Worker
* **Status**: ✅ Implemented
* **Title**: Background Worker Context Isolation
* **Severity**: Low
* **Evidence**:
  In `backend/worker.py` (line 634):
  ```python
  cascade = AICascade()
  ```
* **Exact File**: `backend/worker.py`
* **Exact Function**: Ingestion tasks (e.g., summary generation task)
* **Exact Line Numbers**: 634
* **Runtime Impact**: Background workers execute tasks correctly, but share the inefficient local instantiation pattern, which wastes allocation cycles and isolates connection pools.
* **Root Cause**: Bypassed singleton architecture for `AICascade`.
* **Suggested Fix**: Use the central `AICascade` singleton instance in background tasks.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 23. Legacy Adapter
* **Title**: Heuristic JSON Repair Discarded by Legacy Adapter Re-parsing Raw Responses
* **Severity**: Critical
* **Evidence**:
  In `backend/services/ai_cascade/legacy/adapter.py` (lines 85-110):
  ```python
  # Parse JSON output from execution
  raw_res = result.metadata.get("raw_response", "{}")
  try:
      parsed = json.loads(raw_res)
      ...
  ```
* **Exact File**: `backend/services/ai_cascade/legacy/adapter.py`
* **Exact Function**: `LegacyAdapter.execute_summary_pipeline`
* **Exact Line Numbers**: 85-110
* **Runtime Impact**: If an LLM returns JSON enclosed in markdown blocks, the `ExecutionEngine` successfully repairs and validates the JSON, but the `LegacyAdapter` crashes or fails to parse it because it uses a raw `json.loads` call. This leads to empty tags/context prompts and broken UI rendering.
* **Root Cause**: The legacy adapter was not updated to read the validated fields directly from the returned typed `SummaryResult` object.
* **Suggested Fix**: Refactor `LegacyAdapter` to read fields directly from the `result` object (e.g., `result.summary`, `result.tags`) rather than re-parsing `raw_response`.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 24. Dead Code Detection
* **Status**: 🗑 Dead Code
* **Title**: Orphaned Classes and Frontend Pages Left in Codebase
* **Severity**: Low
* **Evidence**:
  `AIStateMachine` (`state_machine.py`), `QualityValidator` (`quality_validator.py`), `TaskPriority` (`enums.py`), `ocr_worker.py` are dead code. Several frontend files (e.g. `Feed.jsx`, `Reminders.jsx`, `Nebula.jsx`, `Dashboard.jsx`) exist but are never loaded in routing configs.
* **Exact Files**: `backend/services/ai_cascade/state_machine.py`, `backend/services/ocr_worker.py`, `frontend/src/pages/Feed.jsx`, etc.
* **Exact Function**: N/A
* **Exact Line Numbers**: Entire files
* **Runtime Impact**: Unnecessary bundle bloat, technical debt, and import overhead.
* **Root Cause**: Leftover files from previous design iterations.
* **Suggested Fix**: Safely delete the orphaned backend files and frontend pages.
* **Estimated Effort**: Low
* **Risk Level**: Low
* **Dependencies**: None

---

### 25. Architecture Violations
* **Title**: Unauthenticated Telegram Webhook Route and Global Telemetry Metrics Leak
* **Severity**: High
* **Evidence**:
  In `backend/routes/webhook.py` (lines 181-190):
  The webhook parses payloads without verifying `X-Telegram-Bot-Api-Secret-Token`.
  In `backend/routes/metrics.py` (lines 161-191):
  ```python
  return prompt_analytics.get_prompt_metrics(hours=hours) # <-- No user.id isolation!
  ```
* **Exact File**: `backend/routes/webhook.py` & `backend/routes/metrics.py`
* **Exact Function**: `telegram_webhook`, `get_prompts_metrics`, `get_providers_metrics`
* **Exact Line Numbers**: `webhook.py:181-190` and `metrics.py:161-191`
* **Runtime Impact**: Webhook route is vulnerable to request forgery, enabling anyone to push arbitrary tasks. Telemetry routes leak global token usage, costs, and model metrics to any authenticated user.
* **Root Cause**: Lack of webhook authentication and missing user-level isolation in prompt analytics.
* **Suggested Fix**: Verify Telegram Secret Token using `hmac.compare_digest()`, and partition prompt analytics by `user_id` or query filtering.
* **Estimated Effort**: Medium
* **Risk Level**: High
* **Dependencies**: None

---

### 26. Missing V9 Features / Refactoring Opportunities
* **Title**: Duplicate WebSocket Endpoint Implementations and Missing V9 Pipelines
* **Severity**: Medium
* **Evidence**:
  WebSocket connections are registered at `/api/ws` (`backend/routes/api.py:2771`) and `/ws/{token}` (`backend/routes/websocket.py:63`). Missing core pipelines like `TranscriptionPipeline` and `GraphPipeline`.
* **Exact File**: `backend/routes/api.py` & `backend/routes/websocket.py`
* **Exact Function**: `websocket_endpoint`
* **Exact Line Numbers**: `api.py:2771-2801` and `websocket.py:63-189`
* **Runtime Impact**: Duplicate event broadcasting code, disparate authentication flows (cookie vs. token), and inability to route transcription/graph tasks through the cascade.
* **Root Cause**: Legacy endpoints kept alongside newer routes, and incomplete pipeline wiring.
* **Suggested Fix**: Merge both endpoints into a unified `/api/ws` route, and implement the missing pipeline adapters.
* **Estimated Effort**: Medium
* **Risk Level**: Low
* **Dependencies**: Client-side WebSocket hook updates
