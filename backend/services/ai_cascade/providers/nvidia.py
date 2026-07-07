import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class NvidiaProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "nvidia"

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
        if not settings.NVIDIA_API_KEY:
            return None

        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        if model:
            target_model = model
        else:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            target_model = models[0] if models else "meta/llama3-70b-instruct"

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
                logger.warning("NVIDIA NIM rate limited (429).")
                raise RateLimitExceededError(f"NVIDIA rate limit exceeded for {target_model}")
            else:
                logger.warning("NVIDIA NIM call failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"NVIDIA API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.warning("NVIDIA NIM call failed with exception: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"NVIDIA timeout for {target_model}")
            raise ProviderError(f"NVIDIA connection error: {e}")
        return None
