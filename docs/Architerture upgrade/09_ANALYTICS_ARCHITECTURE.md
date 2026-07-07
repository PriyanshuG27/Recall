# Analytics Architecture

## Goal
Track whether Recall is actually useful, fast, reliable, and improving.

## Principle
Analytics is not debugging. Logging is not product analytics. Keep them separate.

## Recommended storage for V1
Use PostgreSQL. It is sufficient for V1 if analytics is designed as:
- event tables
- aggregated tables
- retention policy
- cleanup jobs

## Core tables
### analytics_events
A short-lived event stream.

### analytics_daily
Daily aggregates for dashboard and trends.

### ai_request_metrics
One row per AI request.

### retrieval_metrics
One row per retrieval request.

## Why this works
It keeps raw events limited while still providing meaningful product and system visibility.

## Events to track
### Product
- item_saved
- item_opened
- item_deleted
- item_exported
- search_performed
- zero_result_search
- branch_created
- reminder_created
- reminder_completed
- quiz_generated
- quiz_completed
- login
- logout

### AI
- ai_request_started
- ai_request_succeeded
- ai_request_failed
- fallback_used
- retry_used
- json_repaired

### Retrieval
- retrieval_started
- retrieval_completed
- rerank_used
- graph_search_used
- metadata_filter_used

### System
- upload_failed
- parse_failed
- ocr_failed
- embedding_failed
- worker_retry
- dlq_entry
- cache_hit
- cache_miss

## Metrics to care about
### Product
- DAU
- saves/day
- searches/day
- zero-result rate
- retention

### AI
- latency
- fallback rate
- failure rate
- tokens/request
- cost/request

### Retrieval
- retrieval latency
- reranker improvement
- graph usage
- vector vs BM25 usage

### Infrastructure
- queue depth
- worker failures
- retry rate
- cache hit rate
- DB failures

## Retention strategy
Keep raw events only for 60-90 days, then aggregate and delete them. Keep daily/monthly summaries longer.

## Why not jump to another analytics stack now
ClickHouse, Kafka, or a large observability platform is unnecessary until the system has a much larger scale problem.

## What good looks like
A product dashboard should tell you:
- whether people use Recall
- what they use it for
- where it fails
- what improved after a code change
- whether retrieval and AI are getting better
