import logging
from backend.services.redis_client import redis

logger = logging.getLogger(__name__)

class HealthStore:
    def __init__(self):
        self.redis = redis

    def _consecutive_failures_key(self, provider: str) -> str:
        return f"ai_cascade:health:{provider.lower()}:consecutive_failures"

    def _cooldown_key(self, provider: str) -> str:
        return f"ai_cascade:health:{provider.lower()}:cooldown"

    async def is_healthy(self, provider: str) -> bool:
        """
        Returns True if the provider is healthy (circuit is closed).
        Returns False if the provider is in cooldown (circuit is open).
        """
        try:
            cooldown_active = await self.redis.get(self._cooldown_key(provider))
            if cooldown_active:
                return False
            # Check legacy blocked key for unit tests compatibility
            legacy_active = await self.redis.get(f"ai_breaker:blocked:{provider.lower()}")
            if legacy_active:
                return False
            return True
        except Exception as e:
            logger.error("HealthStore: Failed to check health in Redis: %s", e)
            # Fallback to healthy on Redis errors so we don't block execution
            return True

    async def report_success(self, provider: str) -> None:
        """
        Resets consecutive failures counter and closes the circuit.
        """
        try:
            await self.redis.delete(self._consecutive_failures_key(provider))
            await self.redis.delete(self._cooldown_key(provider))
        except Exception as e:
            logger.error("HealthStore: Failed to report success in Redis: %s", e)

    async def report_failure(self, provider: str, circuit_threshold: int = 3, cooldown_seconds: int = 60) -> None:
        """
        Increments consecutive failure count. If it reaches the threshold, opens the circuit (cooldown).
        """
        try:
            failures_key = self._consecutive_failures_key(provider)
            val = await self.redis.get(failures_key)
            failures = int(val) if val else 0
            failures += 1
            
            await self.redis.setex(failures_key, 3600, str(failures))
            
            if failures >= circuit_threshold:
                logger.warning(
                    "HealthStore: Provider %s exceeded circuit threshold (%d failures). Opening circuit for %d seconds.",
                    provider, circuit_threshold, cooldown_seconds
                )
                await self.redis.setex(self._cooldown_key(provider), cooldown_seconds, "open")
                
                from backend.services.ai_cascade.events.event_bus import event_bus, CircuitBreakerOpened
                await event_bus.publish(CircuitBreakerOpened(
                    provider=provider,
                    consecutive_failures=failures
                ))
        except Exception as e:
            logger.error("HealthStore: Failed to report failure in Redis: %s", e)


health_store = HealthStore()
