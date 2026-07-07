# ADR 007: Use Sentry

## Context
Background workers running AI tasks can crash due to OOM errors, malformed third-party API responses, or bad database connections. These errors often die silently in container logs.

## Decision
Adopt the Sentry SDK for real-time exception tracking.

## Consequences
*   Unhandled exceptions instantly trigger alerts containing the full stack trace, local variables, and the `request_id`.
*   Requires strict configuration to ensure PII and raw encrypted text are scrubbed before transmission.

## Alternatives
*   **Datadog APM:** Expensive and heavy.
*   **Rollbar:** Similar, but Sentry has better Python async integration.

## Tradeoffs
Adding a third-party SaaS dependency for error tracking vs. building a custom exception alerting pipeline.

## Future review trigger
Annual review based on SaaS pricing and volume of tracked errors.
