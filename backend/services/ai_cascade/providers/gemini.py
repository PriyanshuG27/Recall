import base64
import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class GeminiProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def supported_capabilities(self) -> Set[ProviderCapability]:
        return {ProviderCapability.CHAT_COMPLETION, ProviderCapability.TRANSCRIPTION, ProviderCapability.VISION}

    def _convert_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Converts OpenAI system/user messages structure into a flat prompt string for legacy compatibility."""
        prompt_parts = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                prompt_parts.append(f"System Instruction:\n{content}")
            elif role == "user":
                prompt_parts.append(content)
            elif role == "assistant":
                prompt_parts.append(f"Assistant Response:\n{content}")
        return "\n\n".join(prompt_parts)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        if not settings.GEMINI_API_KEY:
            return None

        if model:
            target_model = model
        else:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            target_model = models[0] if models else "gemini-1.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={settings.GEMINI_API_KEY}"
        
        prompt = self._convert_messages_to_prompt(messages)
        
        gen_config = {"temperature": temperature}
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config
        }

        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                # Defensive key extraction (fixing legacy KeyError vulnerability)
                candidates = data.get("candidates")
                if not candidates:
                    logger.warning("Gemini response returned empty candidates block (possibly blocked by safety filters): %s", data)
                    return None
                    
                content_block = candidates[0].get("content")
                if not content_block or not content_block.get("parts"):
                    logger.warning("Gemini candidate did not contain parts block: %s", candidates[0])
                    return None

                text_response = content_block["parts"][0].get("text")
                usage = data.get("usageMetadata", {})
                if usage:
                    logger.info("Gemini API token usage: prompt=%s, candidate=%s, total=%s",
                                usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), usage.get("totalTokenCount"))
                return text_response
            elif resp.status_code == 429:
                logger.warning("Gemini rate limited (429).")
                raise RateLimitExceededError(f"Gemini rate limit exceeded for {target_model}")
            else:
                logger.warning("Gemini call failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"Gemini API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.warning("Gemini call failed with exception: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"Gemini timeout for {target_model}")
            raise ProviderError(f"Gemini connection error: {e}")
        return None

    async def transcribe(
        self,
        audio_bytes: bytes,
        file_extension: str,
        timeout: float
    ) -> Optional[str]:
        if not settings.GEMINI_API_KEY:
            return None

        provider_cfg = cascade_settings.get_provider_config(self.provider_name)
        cfg_models = provider_cfg.get("models", {})
        models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
        target_model = models[0] if models else "gemini-1.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={settings.GEMINI_API_KEY}"
        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        
        mime_mapping = {"ogg": "audio/ogg", "opus": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav"}
        mime_type = mime_mapping.get(file_extension.lower().strip(), "audio/ogg")
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": base64_audio}},
                        {"text": "Transcribe the following audio precisely. Output only the transcription."}
                    ]
                }
            ]
        }
        
        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates")
                if not candidates:
                    logger.warning("Gemini transcription returned empty candidates block: %s", data)
                    return None
                content_block = candidates[0].get("content")
                if not content_block or not content_block.get("parts"):
                    logger.warning("Gemini candidate did not contain parts block: %s", candidates[0])
                    return None
                return content_block["parts"][0].get("text")
            else:
                logger.warning("Gemini transcription failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"Gemini transcription API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.error("Gemini transcription failed: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"Gemini transcription timeout for {target_model}")
            raise ProviderError(f"Gemini transcription connection error: {e}")
        return None

    async def caption_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        timeout: float
    ) -> Optional[str]:
        if not settings.GEMINI_API_KEY:
            return None

        provider_cfg = cascade_settings.get_provider_config(self.provider_name)
        cfg_models = provider_cfg.get("models", {})
        models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
        target_model = models[0] if models else "gemini-1.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={settings.GEMINI_API_KEY}"
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": base64_image}},
                        {"text": "Provide a detailed caption or summary of this image."}
                    ]
                }
            ]
        }
        try:
            client = get_http_client()
            resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates")
                if not candidates:
                    logger.warning("Gemini image captioning returned empty candidates block: %s", data)
                    return None
                content_block = candidates[0].get("content")
                if not content_block or not content_block.get("parts"):
                    logger.warning("Gemini candidate did not contain parts block: %s", candidates[0])
                    return None
                text_response = content_block["parts"][0].get("text")
                return text_response.strip() if text_response else None
            else:
                logger.error("Gemini image captioning failed with status %d: %s", resp.status_code, resp.text)
                raise ProviderError(f"Gemini image captioning API error {resp.status_code}: {resp.text}")
        except (RateLimitExceededError, ProviderError):
            raise
        except Exception as e:
            logger.error("Gemini image captioning failed: %s", e)
            if "timeout" in str(e).lower():
                raise CascadeTimeoutError(f"Gemini image captioning timeout for {target_model}")
            raise ProviderError(f"Gemini image captioning connection error: {e}")
        return None
