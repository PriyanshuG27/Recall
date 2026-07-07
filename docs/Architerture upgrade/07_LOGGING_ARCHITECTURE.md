# Logging Architecture

## Stack

-   Python logging
-   Structlog
-   Sentry

## Features

-   Request IDs
-   Structured JSON logs
-   Stage timings
-   Error codes
-   Redaction
-   Separate app, worker, AI, audit and security logs

## Never Log

Raw documents, OCR text, prompts, secrets, API keys or passwords.
