# ADR 006: Use Structlog

## Context
Debugging asynchronous worker crashes across millions of webhook events is impossible with standard text logs. Log aggregators (Datadog, CloudWatch) require structured data to search effectively.

## Decision
Adopt `structlog` for global JSON-formatted logging.

## Consequences
*   Every log output becomes a JSON object.
*   `ContextVars` can automatically inject the `request_id` and `user_id` into every log line without passing them manually to every function.

## Alternatives
*   **Standard Python logging:** Messy string parsing.
*   **Loguru:** Good, but structlog's processor pipeline is more robust for stripping PII.

## Tradeoffs
Slight verbosity in local development terminals (though mitigatable via `ConsoleRenderer`) in exchange for elite production observability.

## Future review trigger
If the project transitions to a complex microservice architecture that strictly requires OpenTelemetry tracing instead of flat JSON logs.
