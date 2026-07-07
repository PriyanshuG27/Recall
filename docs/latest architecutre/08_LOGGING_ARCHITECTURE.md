# Logging Architecture

## Goal
Make Recall debuggable, observable, and safe without turning logging into a second data leak.

## Recommended stack
- Python built-in logging as the base
- structlog for structured events
- Sentry for error monitoring
- OpenTelemetry later if distributed tracing becomes necessary

## Why not plain text logging
Plain strings are hard to search, hard to aggregate, and too easy to make inconsistent across files.

## What each log should contain
- timestamp
- level
- event
- request_id
- user_id if appropriate
- service
- route or job
- entity type and id
- duration
- status
- error code

## Log categories
- app logs
- API logs
- worker logs
- AI logs
- retrieval logs
- audit logs
- security logs

## Never log
- raw documents
- OCR text
- raw model responses
- secrets
- passwords
- tokens
- `.env` contents
- full prompts containing private text

## Stage timing
Measure durations for:
- upload
- validation
- parsing
- OCR
- chunking
- embedding
- retrieval
- reranking
- AI synthesis
- graph update
- save/delete

## Error codes
Use stable codes such as:
- AUTH_FAILED
- UPLOAD_INVALID
- PARSE_FAILED
- OCR_FAILED
- AI_TIMEOUT
- AI_PARSE_FAILED
- DB_WRITE_FAILED
- CACHE_WRITE_FAILED

## Request correlation
Every request should have a request_id so a single action can be traced across:
- API
- worker
- AI
- DB
- cache
- graph updates

## Why structlog is the right fit
It provides structured event logging without forcing Recall into a heavyweight logging stack. The benefit is future compatibility with search, dashboards, and alerting.

## Sentry role
Sentry captures stack traces, breadcrumbs, and release-level errors. It is complementary to logs, not a replacement.

## Migration strategy
1. Create one central logging module.
2. Add request ID middleware.
3. Replace print calls.
4. Add redaction filters.
5. Standardize event names.
6. Add Sentry.
7. Later, add tracing if needed.

## What good looks like
A log entry should be understandable by both a human and a machine.
