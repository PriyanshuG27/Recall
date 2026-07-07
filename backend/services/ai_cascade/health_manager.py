import time
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class HealthManager:
    # State tracking: (provider, model) -> { "fails": int, "blocked_until": float }
    _states: Dict[Tuple[str, str], dict] = {}
    
    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 120
    RATE_LIMIT_COOLDOWN = 60

    @classmethod
    def get_state_key(cls, provider: str, model: str) -> Tuple[str, str]:
        return (provider.lower().strip(), model.lower().strip())

    @classmethod
    def is_healthy(cls, provider: str, model: str) -> bool:
        key = cls.get_state_key(provider, model)
        state = cls._states.get(key)
        if not state:
            return True
            
        blocked_until = state.get("blocked_until", 0.0)
        if blocked_until > time.time():
            return False
            
        # Cooldown expired, reset failure count (half-open phase)
        if blocked_until > 0:
            logger.info("Circuit breaker cooldown expired for %s:%s. Resetting state.", provider, model)
            state["fails"] = 0
            state["blocked_until"] = 0.0
            
        return True

    @classmethod
    def record_failure(cls, provider: str, model: str, error_type: str = "error") -> None:
        key = cls.get_state_key(provider, model)
        if key not in cls._states:
            cls._states[key] = {"fails": 0, "blocked_until": 0.0}
            
        state = cls._states[key]
        
        if error_type == "rate_limit":
            # 429 triggers a 60 second block immediately
            state["blocked_until"] = time.time() + cls.RATE_LIMIT_COOLDOWN
            logger.warning("Rate limit 429 recorded for %s:%s. Blocking for %d seconds.", provider, model, cls.RATE_LIMIT_COOLDOWN)
        else:
            state["fails"] += 1
            if state["fails"] >= cls.FAILURE_THRESHOLD:
                state["blocked_until"] = time.time() + cls.COOLDOWN_SECONDS
                logger.error("Circuit breaker tripped for %s:%s. Tripped on %d consecutive failures. Blocking for %d seconds.", provider, model, state["fails"], cls.COOLDOWN_SECONDS)

    @classmethod
    def record_success(cls, provider: str, model: str) -> None:
        key = cls.get_state_key(provider, model)
        if key in cls._states:
            cls._states[key]["fails"] = 0
            cls._states[key]["blocked_until"] = 0.0
