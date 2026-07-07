# ADR 008: Use PostgreSQL for Analytics

## Context
Recall needs to track product usage (searches, saves) and AI telemetry (tokens, USD costs). Currently, this is stored in memory and lost on restart, or leaked globally.

## Decision
Build a custom async telemetry logger that writes `analytics_events` and `telemetry_cost_logs` directly into PostgreSQL. 

## Consequences
*   100% data retention on worker restarts.
*   Strict enforcement of `user_id` filtering, solving the global metric leak.
*   No third-party trackers receive user behavioral data.

## Alternatives
*   **PostHog / Mixpanel:** Powerful, but introduces significant privacy policy complications.
*   **ClickHouse:** Optimal for analytics, but adds a second database.

## Tradeoffs
Postgres is not an OLAP database; querying millions of analytic rows will eventually become slow. We trade ultimate analytical scale for strict privacy and operational simplicity in V1.

## Future review trigger
When the `analytics_events` table exceeds 10 million rows per month, triggering the need for a dedicated OLAP database like ClickHouse.
