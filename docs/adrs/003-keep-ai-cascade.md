# ADR 003: Keep AI Cascade Orchestrator

## Context
Orchestrating LLM interactions involves complex routing, exponential backoffs for rate limits, circuit breakers, and strict concurrency controls. Standard API calls are insufficient.

## Decision
Keep and mandate the usage of the custom `AICascade` orchestrator for 100% of LLM executions. Treat it as an immutable architectural boundary.

## Consequences
*   Every LLM call benefits from the `RetryEngine`, `SecurityLayer`, and `PersistenceManager`.
*   Forces developers to write strict schemas and Jinja pipelines rather than hacking together quick prompt strings.

## Alternatives
*   **Direct API Calls:** Brittle, fail under load, lack observability.
*   **LangChain:** Too bloated and unpredictable.

## Tradeoffs
High initial engineering effort to build and maintain the orchestration framework in exchange for absolute control, determinism, and vendor-agnostic routing.

## Future review trigger
Never. This is a hard architectural constraint of the Recall project.
