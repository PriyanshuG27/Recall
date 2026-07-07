import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class OpenRouterProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def supported_capabilities(self) -> Set[ProviderCapability]:
        return {ProviderCapability.CHAT_COMPLETION}

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        if not settings.OPENROUTER_API_KEY:
            return None

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        if model:
            target_model = model
        else:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            target_model = models[0] if models else "openai/gpt-4o-mini"

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            elif resp.status_code == 429:
                logger.warning("OpenRouter rate limited (429).")
                raise RateLimitExceededError(f"OpenRouter rate limit exceeded for {target_model}")
            else:
                logger.warning("OpenRouter call failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"OpenRouter API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.warning("OpenRouter call failed with exception: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"OpenRouter timeout for {target_model}")
            raise ProviderError(f"OpenRouter connection error: {e}")
        return None
