import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class CerebrasProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "cerebras"

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
        # Cerebras API token validation
        cerebras_key = getattr(settings, "CEREBRAS_API_KEY", None)
        if not cerebras_key:
            return None

        url = "https://api.cerebras.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {cerebras_key}",
            "Content-Type": "application/json"
        }
        
        if model:
            model_name = model
        else:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            model_name = models[0] if models else "llama3.1-8b"

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            elif resp.status_code == 429:
                logger.warning("Cerebras API Rate Limited (429).")
                raise RateLimitExceededError(f"Cerebras rate limit exceeded for {model_name}")
            else:
                logger.warning("Cerebras call failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"Cerebras API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.warning("Cerebras call failed with exception: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"Cerebras timeout for {model_name}")
            raise ProviderError(f"Cerebras connection error: {e}")
        return None
