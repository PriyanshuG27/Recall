# ADR 002: Keep FastAPI

## Context
The Recall backend must process highly concurrent Telegram webhook requests. Webhooks must return an HTTP 200 acknowledgment within 50ms to prevent Telegram from dropping the connection or entering infinite retry loops.

## Decision
Keep FastAPI as the core web framework.

## Consequences
*   Native async/await support ensures the web server can handle thousands of concurrent connections without blocking threads.
*   Pydantic integration perfectly complements the AI validation logic (Instructor).

## Alternatives
*   **Django:** Excellent ORM and admin panel, but async support is bolted-on and heavier.
*   **Flask:** Lacks native, modern async typing and built-in validation.

## Tradeoffs
We lose out-of-the-box admin panels and robust built-in ORMs (like Django provides), but gain the extreme asynchronous throughput required for an AI gateway.

## Future review trigger
Never. The framework is deeply embedded and perfectly suited for the task.
