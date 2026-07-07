import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class PromptAnalyticsManager:
    def __init__(self):
        # time_bucket (YYYY-MM-DDTHH) -> pipeline -> prompt_version -> model -> provider -> stats
        self._stats: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]]] = {}
        
        # request_id -> { "attempts": int, "pipeline": str, "prompt_version": str, "time_bucket": str, "failed": bool }
        self._request_tracker: Dict[str, Dict[str, Any]] = {}
        self._is_subscribed = False

    def initialize(self) -> None:
        """Subscribe analytics manager callbacks to the event bus."""
        if self._is_subscribed:
            return
        try:
            from backend.services.ai_cascade.events.event_bus import event_bus, LLMRequestFinished, CacheHit
            
            # EventHandler Protocol expects an object with 'handle' method
            class RequestFinishedHandler:
                def __init__(self, manager: 'PromptAnalyticsManager'):
                    self.manager = manager
                async def handle(self, event: LLMRequestFinished) -> None:
                    await self.manager.handle_request_finished(event)

            class CacheHitHandler:
                def __init__(self, manager: 'PromptAnalyticsManager'):
                    self.manager = manager
                async def handle(self, event: CacheHit) -> None:
                    await self.manager.handle_cache_hit(event)

            event_bus.subscribe(LLMRequestFinished, RequestFinishedHandler(self))
            event_bus.subscribe(CacheHit, CacheHitHandler(self))
            self._is_subscribed = True
            logger.info("PromptAnalyticsManager successfully subscribed to EventBus.")
        except Exception as e:
            logger.warning("PromptAnalyticsManager: failed to subscribe: %s", e)

    def shutdown(self) -> None:
        """Clear stats data."""
        self._stats.clear()
        self._request_tracker.clear()
        self._is_subscribed = False

    def get_time_bucket(self, dt: datetime) -> str:
        """Returns UTC hourly time bucket format YYYY-MM-DDTHH."""
        dt_utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H")

    def _get_stats_node(self, user_id: Optional[int], time_bucket: str, pipeline: str, prompt_version: str, model: str, provider: str) -> Dict[str, Any]:
        user_dict = self._stats.setdefault(user_id, {})
        p_dict = user_dict.setdefault(time_bucket, {})
        pipe_dict = p_dict.setdefault(pipeline, {})
        ver_dict = pipe_dict.setdefault(prompt_version, {})
        mod_dict = ver_dict.setdefault(model, {})
        return mod_dict.setdefault(provider, {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "cache_hits": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
            "latencies": [],
            "unique_runs": set(),      # set of request_ids
            "fallback_runs": set()     # set of request_ids that suffered >=1 failure
        })

    async def handle_request_finished(self, event: Any) -> None:
        tb = self.get_time_bucket(event.timestamp)
        pipeline = event.pipeline or "unknown"
        prompt_version = event.prompt_version or "unknown"
        model = event.model
        provider = event.provider
        user_id = getattr(event, "user_id", None)

        node = self._get_stats_node(user_id, tb, pipeline, prompt_version, model, provider)

        # Track unique request_id runs and fallbacks
        if event.request_id:
            req_id = event.request_id
            node["unique_runs"].add(req_id)
            
            tracker = self._request_tracker.setdefault(req_id, {
                "attempts": 0,
                "pipeline": pipeline,
                "prompt_version": prompt_version,
                "time_bucket": tb,
                "failed": False
            })
            tracker["attempts"] += 1
            if not event.success:
                tracker["failed"] = True
                node["fallback_runs"].add(req_id)

        node["total_calls"] += 1
        if event.success:
            node["success_calls"] += 1
            node["latencies"].append(event.latency_ms)
        else:
            node["failed_calls"] += 1

        node["prompt_tokens"] += event.prompt_tokens
        node["completion_tokens"] += event.completion_tokens

        from backend.services.ai_cascade.telemetry.cost_manager import CostManager
        cost = CostManager.calculate_cost(
            provider=provider,
            model=model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            duration_seconds=event.latency_ms / 1000.0
        )
        node["estimated_cost_usd"] += cost

        # Log usage details to database telemetry cost logs table
        await CostManager.log_usage(
            provider=provider,
            model=model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            duration_seconds=event.latency_ms / 1000.0
        )

    async def handle_cache_hit(self, event: Any) -> None:
        tb = self.get_time_bucket(event.timestamp)
        pipeline = event.pipeline or "unknown"
        prompt_version = "cached"
        model = "cached"
        provider = "cached"
        user_id = getattr(event, "user_id", None)

        node = self._get_stats_node(user_id, tb, pipeline, prompt_version, model, provider)
        node["total_calls"] += 1
        node["cache_hits"] += 1
        if event.request_id:
            node["unique_runs"].add(event.request_id)

    def get_prompt_metrics(self, user_id: Optional[int] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Gathers metrics statistics comparison grouped by pipeline and prompt version."""
        now = datetime.now(timezone.utc)
        target_buckets = {self.get_time_bucket(now - timedelta(hours=h)) for h in range(hours)}

        aggregated: Dict[tuple, Dict[str, Any]] = {}

        user_stats = self._stats.get(user_id, {})
        for tb, p_dict in user_stats.items():
            if tb not in target_buckets:
                continue
            for pipeline, ver_dict in p_dict.items():
                for prompt_version, mod_dict in ver_dict.items():
                    key = (pipeline, prompt_version)
                    agg = aggregated.setdefault(key, {
                        "pipeline": pipeline,
                        "prompt_version": prompt_version,
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "cache_hits": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "estimated_cost_usd": 0.0,
                        "latencies": [],
                        "unique_runs": set(),
                        "fallback_runs": set()
                    })

                    for model, prov_dict in mod_dict.items():
                        for provider, node in prov_dict.items():
                            agg["total_calls"] += node["total_calls"]
                            agg["success_calls"] += node["success_calls"]
                            agg["failed_calls"] += node["failed_calls"]
                            agg["cache_hits"] += node["cache_hits"]
                            agg["prompt_tokens"] += node["prompt_tokens"]
                            agg["completion_tokens"] += node["completion_tokens"]
                            agg["estimated_cost_usd"] += node["estimated_cost_usd"]
                            agg["latencies"].extend(node["latencies"])
                            agg["unique_runs"].update(node["unique_runs"])
                            agg["fallback_runs"].update(node["fallback_runs"])

        results = []
        for (pipeline, ver), agg in aggregated.items():
            total_runs = len(agg["unique_runs"])
            fallback_runs = len(agg["fallback_runs"])
            fallback_rate = (fallback_runs / total_runs) if total_runs > 0 else 0.0
            
            avg_lat = sum(agg["latencies"]) / len(agg["latencies"]) if agg["latencies"] else 0.0
            success_rate = (agg["success_calls"] / agg["total_calls"]) if agg["total_calls"] > 0 else 0.0
            cache_hit_rate = (agg["cache_hits"] / agg["total_calls"]) if agg["total_calls"] > 0 else 0.0

            results.append({
                "pipeline": pipeline,
                "prompt_version": ver,
                "total_calls": agg["total_calls"],
                "success_rate": round(success_rate, 4),
                "cache_hit_rate": round(cache_hit_rate, 4),
                "fallback_rate": round(fallback_rate, 4),
                "avg_latency_ms": round(avg_lat, 2),
                "prompt_tokens": agg["prompt_tokens"],
                "completion_tokens": agg["completion_tokens"],
                "total_tokens": agg["prompt_tokens"] + agg["completion_tokens"],
                "estimated_cost_usd": round(agg["estimated_cost_usd"], 6)
            })
        return results

    def get_provider_metrics(self, user_id: Optional[int] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Gathers metric statistics for provider dashboards."""
        now = datetime.now(timezone.utc)
        target_buckets = {self.get_time_bucket(now - timedelta(hours=h)) for h in range(hours)}

        aggregated: Dict[tuple, Dict[str, Any]] = {}

        user_stats = self._stats.get(user_id, {})
        for tb, p_dict in user_stats.items():
            if tb not in target_buckets:
                continue
            for pipeline, ver_dict in p_dict.items():
                for prompt_version, mod_dict in ver_dict.items():
                    for model, prov_dict in mod_dict.items():
                        if model == "cached":
                            continue
                        for provider, node in prov_dict.items():
                            key = (provider, model)
                            agg = aggregated.setdefault(key, {
                                "provider": provider,
                                "model": model,
                                "total_calls": 0,
                                "success_calls": 0,
                                "failed_calls": 0,
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "estimated_cost_usd": 0.0,
                                "latencies": [],
                                "unique_runs": set(),
                                "fallback_runs": set()
                            })
                            agg["total_calls"] += node["total_calls"]
                            agg["success_calls"] += node["success_calls"]
                            agg["failed_calls"] += node["failed_calls"]
                            agg["prompt_tokens"] += node["prompt_tokens"]
                            agg["completion_tokens"] += node["completion_tokens"]
                            agg["estimated_cost_usd"] += node["estimated_cost_usd"]
                            agg["latencies"].extend(node["latencies"])
                            agg["unique_runs"].update(node["unique_runs"])
                            agg["fallback_runs"].update(node["fallback_runs"])

        results = []
        for (provider, model), agg in aggregated.items():
            total_runs = len(agg["unique_runs"])
            fallback_runs = len(agg["fallback_runs"])
            
            avg_lat = sum(agg["latencies"]) / len(agg["latencies"]) if agg["latencies"] else 0.0
            availability_rate = (agg["success_calls"] / agg["total_calls"]) if agg["total_calls"] > 0 else 0.0
            
            results.append({
                "provider": provider,
                "model": model,
                "total_calls": agg["total_calls"],
                "availability": round(availability_rate * 100.0, 2),
                "avg_latency_ms": round(avg_lat, 2),
                "prompt_tokens": agg["prompt_tokens"],
                "completion_tokens": agg["completion_tokens"],
                "total_tokens": agg["prompt_tokens"] + agg["completion_tokens"],
                "estimated_cost_usd": round(agg["estimated_cost_usd"], 6),
                "fallback_frequency": round((fallback_runs / total_runs) * 100.0, 2) if total_runs > 0 else 0.0
            })
        return results


prompt_analytics = PromptAnalyticsManager()
