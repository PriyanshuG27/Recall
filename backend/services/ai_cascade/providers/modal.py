import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class ModalProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "modal"

    @property
    def supported_capabilities(self) -> Set[ProviderCapability]:
        return {ProviderCapability.CHAT_COMPLETION, ProviderCapability.TRANSCRIPTION}

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        if not settings.MODAL_API_TOKEN:
            return None

        # Extract primary content text from the messages
        prompt = messages[-1].get("content", "") if messages else ""
        headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
        client = get_http_client()

        target_model = model
        if not target_model:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            target_model = models[0] if models else "modal-summary"

        model_type = "summary"
        if "summary" in target_model.lower():
            model_type = "summary"
        elif "tags" in target_model.lower():
            model_type = "tags"
        else:
            model_type = "rag"

        # Route dynamically based on the requested modal service override
        if model_type == "summary":
            url = settings.MODAL_SUMMARY_URL or "https://modal.run/summarize"
            try:
                resp = await client.post(url, json={"text": prompt}, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json().get("summary")
                elif resp.status_code == 429:
                    raise RateLimitExceededError("Modal summary rate limited (429)")
                else:
                    raise ProviderError(f"Modal summary failed with status {resp.status_code}: {resp.text}")
            except (RateLimitExceededError, ProviderError):
                raise
            except Exception as e:
                logger.warning("Modal summary request failed: %s", e)
                if "timeout" in str(e).lower():
                    raise CascadeTimeoutError("Modal summary request timeout")
                raise ProviderError(f"Modal summary connection error: {e}")
        elif model_type == "tags":
            # For tags, extract context from system instruction if any
            context = messages[0].get("content", "") if len(messages) > 1 else ""
            url = settings.MODAL_TAGS_URL or "https://modal.run/generate-tags"
            try:
                resp = await client.post(url, json={"text": context, "prompt": prompt}, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json().get("tags_raw")
                elif resp.status_code == 429:
                    raise RateLimitExceededError("Modal tags rate limited (429)")
                else:
                    raise ProviderError(f"Modal tags failed with status {resp.status_code}: {resp.text}")
            except (RateLimitExceededError, ProviderError):
                raise
            except Exception as e:
                logger.warning("Modal generate-tags request failed: %s", e)
                if "timeout" in str(e).lower():
                    raise CascadeTimeoutError("Modal tags request timeout")
                raise ProviderError(f"Modal tags connection error: {e}")
        else:
            # Default to RAG
            url = settings.MODAL_RAG_URL or "https://modal.run/rag"
            try:
                resp = await client.post(url, json={"prompt": prompt}, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json().get("answer")
                elif resp.status_code == 429:
                    raise RateLimitExceededError("Modal RAG rate limited (429)")
                else:
                    raise ProviderError(f"Modal RAG failed with status {resp.status_code}: {resp.text}")
            except (RateLimitExceededError, ProviderError):
                raise
            except Exception as e:
                logger.warning("Modal RAG request failed: %s", e)
                if "timeout" in str(e).lower():
                    raise CascadeTimeoutError("Modal RAG request timeout")
                raise ProviderError(f"Modal RAG connection error: {e}")

        return None

    async def transcribe(
        self,
        audio_bytes: bytes,
        file_extension: str,
        timeout: float
    ) -> Optional[str]:
        if not settings.MODAL_API_TOKEN:
            return None

        url = settings.MODAL_TRANSCRIBE_URL or "https://modal.run/transcribe"
        headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
        
        try:
            client = get_http_client()
            resp = await client.post(url, content=audio_bytes, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json().get("transcript")
            elif resp.status_code == 429:
                raise RateLimitExceededError("Modal transcription rate limited (429)")
            else:
                raise ProviderError(f"Modal transcription failed with status {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.warning("Modal transcription failed: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError("Modal transcription request timeout")
            raise ProviderError(f"Modal transcription connection error: {e}")
        return None
