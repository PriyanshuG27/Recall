from backend.services.ai_cascade.cache_manager import CacheManager as RedisCacheManager
from backend.services.ai_cascade.cache.health_store import HealthStore, health_store

cache_manager = RedisCacheManager()
__all__ = ["cache_manager", "health_store"]
