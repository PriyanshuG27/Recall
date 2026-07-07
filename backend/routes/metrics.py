import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException

import psycopg
from backend.db.connection import get_db
from backend.middleware.twa_auth import get_current_user, UserContext
from backend.services.rate_limiter import rate_limit
from backend.services.redis_client import redis

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["Metrics & Monitoring"],
    dependencies=[Depends(rate_limit("metrics", 30))]  # rate limit 30 calls per minute
)


@router.get("/ai")
async def get_ai_metrics(
    hours: int = Query(default=24, ge=1, le=720, description="Time window in hours (1 to 720)"),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
) -> Dict[str, Any]:
    """
    Exposes token consumption, USD costs, latencies, and success ratios for the current user.
    """
    user_id = user.id

    try:
        async with db.cursor() as cur:
            # 1. Query token consumption and costs from telemetry_cost_logs
            # Interval is parameterized securely by constructing a timedelta or parameterizing hours
            await cur.execute(
                """
                SELECT 
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(cost_usd), 0.0) as total_cost_usd
                FROM telemetry_cost_logs
                WHERE user_id = %s AND created_at >= NOW() - %s * INTERVAL '1 hour'
                """,
                (user_id, hours)
            )
            cost_row = await cur.fetchone()
            cost_data = {
                "prompt_tokens": int(cost_row[0]) if cost_row else 0,
                "completion_tokens": int(cost_row[1]) if cost_row else 0,
                "total_tokens": int(cost_row[2]) if cost_row else 0,
                "total_cost_usd": float(cost_row[3]) if cost_row else 0.0
            }

            # 2. Query attempts and success logs from ai_decision_logs
            await cur.execute(
                """
                SELECT attempts, success
                FROM ai_decision_logs
                WHERE user_id = %s AND created_at >= NOW() - %s * INTERVAL '1 hour'
                """,
                (user_id, hours)
            )
            rows = await cur.fetchall()

        total_calls = len(rows)
        success_calls = 0
        provider_stats = {}

        for row in rows:
            attempts = row[0] or []
            success = row[1]
            if success:
                success_calls += 1

            for att in attempts:
                provider = att.get("provider", "unknown")
                model = att.get("model", "unknown")
                status = att.get("status", "unknown")
                latency = att.get("latency_ms", 0.0)

                key = f"{provider}:{model}"
                stats = provider_stats.setdefault(key, {"calls": 0, "failures": 0, "latencies": []})
                stats["calls"] += 1
                if status == "failed":
                    stats["failures"] += 1
                if latency > 0:
                    stats["latencies"].append(latency)

        # Post-process provider statistics
        provider_breakdown = {}
        for key, stats in provider_stats.items():
            lats = stats["latencies"]
            avg_latency = sum(lats) / len(lats) if lats else 0.0
            provider_breakdown[key] = {
                "total_calls": stats["calls"],
                "failure_rate": stats["failures"] / stats["calls"] if stats["calls"] > 0 else 0.0,
                "avg_latency_ms": round(avg_latency, 2)
            }

        success_ratio = success_calls / total_calls if total_calls > 0 else 1.0

        return {
            "window_hours": hours,
            "summary": {
                "total_calls": total_calls,
                "success_ratio": round(success_ratio, 4),
                "success_calls": success_calls,
                "failed_calls": total_calls - success_calls
            },
            "costs": cost_data,
            "provider_breakdown": provider_breakdown
        }

    except Exception as err:
        logger.error("Failed to compile AI metrics: %s", err)
        raise HTTPException(status_code=500, detail="Failed to retrieve monitoring metrics.")


@router.get("/health")
async def get_provider_health(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns the real-time circuit breaker status and consecutive failures count from Redis
    for all registered AI providers.
    """
    providers = ["groq", "gemini", "openrouter", "modal", "nvidia", "cerebras"]
    health_status = {}

    for provider in providers:
        try:
            consec_failures_key = f"ai_cascade:health:consecutive_failures:{provider}"
            cooldown_key = f"ai_cascade:health:cooldown:{provider}"

            failures_val = await redis.get(consec_failures_key)
            cooldown_val = await redis.get(cooldown_key)

            consecutive_failures = int(failures_val) if failures_val else 0
            in_cooldown = cooldown_val is not None

            health_status[provider] = {
                "status": "unhealthy" if in_cooldown else "healthy",
                "consecutive_failures": consecutive_failures,
                "in_cooldown": in_cooldown
            }
        except Exception as err:
            logger.warning("Failed to check Redis health key for provider %s: %s", provider, err)
            health_status[provider] = {
                "status": "unknown",
                "consecutive_failures": 0,
                "in_cooldown": False
            }

    return {
        "status": "ok",
        "providers": health_status
    }


@router.get("/prompts")
async def get_prompts_metrics(
    hours: int = Query(default=24, ge=1, le=720, description="Time window in hours (1 to 720)"),
    user: UserContext = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Returns prompt version performance comparison metrics bucketed by hour.
    """
    try:
        from backend.services.ai_cascade.analytics.prompt_analytics import prompt_analytics
        return prompt_analytics.get_prompt_metrics(user_id=user.id, hours=hours)
    except Exception as err:
        logger.error("Failed to retrieve prompts metrics: %s", err)
        raise HTTPException(status_code=500, detail="Failed to retrieve prompts metrics.")


@router.get("/providers")
async def get_providers_metrics(
    hours: int = Query(default=24, ge=1, le=720, description="Time window in hours (1 to 720)"),
    user: UserContext = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Returns detailed operational provider dashboard metrics (availability, fallback frequency, latencies, tokens).
    """
    try:
        from backend.services.ai_cascade.analytics.prompt_analytics import prompt_analytics
        return prompt_analytics.get_provider_metrics(user_id=user.id, hours=hours)
    except Exception as err:
        logger.error("Failed to retrieve providers metrics: %s", err)
        raise HTTPException(status_code=500, detail="Failed to retrieve providers metrics.")

