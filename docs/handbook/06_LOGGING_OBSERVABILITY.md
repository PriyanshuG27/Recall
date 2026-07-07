# Chapter 6: Logging & Production Observability

## 1. Introduction
A system as complex as Recall—orchestrating webhooks, AI providers, relational databases, and asynchronous workers—cannot be debugged via standard `print` statements. This chapter defines the logging and observability architecture required to make the system transparent, debuggable, and safe for production, without turning logs into a secondary privacy leak.

## 2. Current Recall implementation
Recall's current logging is inconsistent, relying heavily on standard Python `logging` and ad-hoc `print` calls. Errors in the AI Cascade are often swallowed by provider adapters and reduced to simple warnings. 
While a `telemetry_cost_logs` table exists, the execution engine currently bypasses logging for critical pipelines (like the summary pipeline). Metrics are aggregated globally in memory via `PromptAnalyticsManager`, leading to data loss on restart and potential data leaks across users.

## 3. Problems
*   **Stringly-Typed Logs:** Standard text logs are difficult to parse in log aggregators (like Datadog or AWS CloudWatch).
*   **Missing Request Correlation:** An error in the background worker cannot be easily traced back to the original Telegram webhook request.
*   **Secret/PII Leakage:** Raw prompts and full LLM outputs risk being written to console logs during exceptions.
*   **Swallowed Exceptions:** Provider adapters catch all exceptions internally (returning `None`), blinding the system to rate limits (429s) and hiding the root cause of failures from the logs.
*   **No Centralized Error Monitoring:** Without a tool like Sentry, stack traces are buried in container stdout streams.

## 4. Design Goals
*   **Structured Events:** Use JSON-formatted structured logging (`structlog`) for all application logs.
*   **Traceability:** Every action must carry a `request_id` that spans from the API layer through the queue to the worker and database.
*   **Privacy by Default:** Logs must never contain raw document text, unencrypted tokens, or passwords.
*   **Separation of Concerns:** Differentiate between application logs (for debugging), error tracking (Sentry), and product analytics (database).

## 5. Architecture
1.  **Logging Engine:** `structlog` wraps the standard Python logger, outputting JSON lines in production and colorized text in local development.
2.  **Context Variables:** ContextVars store the `request_id` and `user_id` so they are automatically injected into every log emitted during a request lifecycle.
3.  **Redaction Filters:** A structlog processor scans log values and masks known sensitive keys (e.g., `api_key`, `prompt`, `raw_text`).
4.  **Error Monitoring:** Sentry SDK intercepts unhandled exceptions and routes them to a centralized dashboard, attaching the `request_id` and local variables.

## 6. Data Flow
1.  A webhook arrives. The FastAPI middleware generates a UUID `request_id` and sets it in a ContextVar.
2.  The middleware logs: `{"event": "request_started", "request_id": "123", "method": "POST"}`.
3.  The task is queued, and the `request_id` is included in the JSON payload.
4.  The worker pops the task, sets the ContextVar to the extracted `request_id`.
5.  If the AI provider fails, an exception is raised.
6.  Sentry catches the exception and transmits the stack trace.
7.  `structlog` emits a JSON error log containing the exact `request_id` for correlation.

## 7. Diagrams

```mermaid
flowchart TD
    A[FastAPI Middleware] -->|Generates request_id| B(ContextVar)
    B --> C[Webhook Log]
    B --> D[Redis Queue Payload]
    
    D --> E[Worker Process]
    E -->|Restores request_id| F(Worker ContextVar)
    F --> G[structlog processor]
    F --> H[Sentry SDK]
    
    G --> I[JSON Log Stream (stdout)]
    H --> J[Sentry Dashboard]
```

## 8. Interfaces
*   **Structlog Implementation Example:**
    ```python
    import structlog
    
    logger = structlog.get_logger("recall.ai")
    logger.info("ai_request_completed", provider="groq", duration_ms=450, tokens=120)
    ```

## 9. Database Changes
*   Observability relies entirely on external log aggregators and Sentry. No direct PostgreSQL schema changes are required for standard application logging.

## 10. Folder Structure
*   `backend/core/logging.py`: Central `structlog` configuration and processor definitions.
*   `backend/middleware/request_id.py`: FastAPI middleware for ContextVar injection.

## 11. API Changes
*   All FastAPI responses will include an `X-Request-ID` header so clients can report specific trace IDs if they encounter errors.

## 12. Migration Strategy
1.  Introduce `structlog` and configure it to output JSON in the production environment variables.
2.  Add the `request_id` middleware and inject it into the Redis task payload.
3.  Globally search and replace standard `logging` and `print` calls with `structlog.get_logger()`.
4.  Integrate the Sentry SDK in `main.py` and `worker.py`.

## 13. Rollback Strategy
If the JSON log volume overloads the container's stdout buffer or the log aggregator, the structlog formatter can be toggled back to a standard concise text format via an environment variable (`LOG_FORMAT=text`).

## 14. Performance
*   **Logging Overhead:** JSON serialization via `structlog` is highly optimized but not free. Keep log payloads flat and avoid dumping massive nested dictionaries into log values.
*   **Sentry Overhead:** Sentry should be configured to drop transactions if volume spikes, using a sample rate (e.g., `traces_sample_rate=0.1`) to prevent performance degradation.

## 15. Failure Modes
*   **ContextVar Bleed:** If ContextVars are not properly managed in asynchronous loops, a `request_id` from one user might bleed into another's log. Strict scoped execution is required.
*   **Logging Crashes:** If a redaction filter crashes while processing a log, it must safely fail open (dropping the log entirely) rather than crashing the main application thread.

## 16. Security Considerations
*   **Log Redaction:** The structlog pipeline must include a processor that actively redacts keys matching `*token*`, `*password*`, `*secret*`, `*key*`, and `raw_text`.
*   **Sentry Scrubbing:** Sentry must be configured in the UI to scrub PII and prevent raw request bodies from being sent to their servers.

## 17. Complexity Analysis
*   **Time Complexity:** O(1) per log statement.
*   **Space Complexity:** O(1) for ContextVar allocation per request.

## 18. Tradeoffs
*   **Structlog vs. OpenTelemetry:** While OpenTelemetry provides superior distributed tracing, it is excessively complex for V1. Structlog with shared `request_id` provides 90% of the value with 10% of the setup effort.

## 19. Alternatives Considered
*   **Logstash / ELK Stack:** Rejected. Running an ELK stack is a massive infrastructure burden. Logs should simply stream to standard output, allowing PaaS providers (Render/Koyeb) to handle aggregation.

## 20. Final Recommendation
Adopt `structlog` for structured JSON logging and Sentry for error tracking. Implement a strict `request_id` correlation pattern across the API and Worker boundaries.

## 21. Implementation Checklist
*   [ ] Configure `structlog` globally in `backend/core/logging.py`.
*   [ ] Implement FastAPI `X-Request-ID` middleware.
*   [ ] Update the Redis task queue to pass `request_id` to the worker.
*   [ ] Refactor provider adapters to raise exceptions instead of swallowing them.
*   [ ] Integrate Sentry SDK.

## 22. Future Improvements
*   Implement full OpenTelemetry tracing when the architecture splits into distinct microservices.
*   Create automated Datadog/Grafana dashboards reading from the JSON log stream.

## 23. Version
1.0.0

## 24. Priority
P1 - High (Essential for production stability)

## 25. Estimated Engineering Effort
3 Developer Days.
