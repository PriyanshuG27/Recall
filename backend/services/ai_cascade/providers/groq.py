import logging
from typing import List, Dict, Optional, Set
from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.shared.exceptions import ProviderError, RateLimitExceededError, CascadeTimeoutError
from backend.services.ai_cascade.config import settings as cascade_settings

logger = logging.getLogger(__name__)

class GroqProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "groq"

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
        if not settings.GROQ_API_KEY:
            return None

        # 1. Select models dynamically from config
        if model:
            models = [model]
        else:
            provider_cfg = cascade_settings.get_provider_config(self.provider_name)
            cfg_models = provider_cfg.get("models", {})
            models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
            if not models:
                models = ["llama-3.3-70b-versatile"]
        
        # 2. Dynamic Token calculation (legacy logic)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        est_prompt_tokens = int(total_chars / 3.0)
        calculated_max_tokens = min(2048, max(512, 7400 - est_prompt_tokens))
        target_max_tokens = max_tokens or calculated_max_tokens

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        client = get_http_client()

        for current_model in models:
            payload_messages = messages
            
            # Apply Qwen JSON modifications (legacy logic)
            if "qwen" in current_model.lower() and json_mode:
                payload_messages = []
                has_system = False
                for m in messages:
                    if m.get("role") == "system":
                        has_system = True
                        payload_messages.append({
                            "role": "system",
                            "content": m.get("content", "") + "\n\nCRITICAL: Do NOT write any thinking process, reasoning, explanation, or <think> tags. Start immediately with the JSON block and output ONLY the raw JSON."
                        })
                    else:
                        payload_messages.append(m)
                if not has_system:
                    payload_messages.insert(0, {
                        "role": "system",
                        "content": "CRITICAL: Do NOT write any thinking process, reasoning, explanation, or <think> tags. Start immediately with the JSON block and output ONLY the raw JSON."
                    })
            elif json_mode:
                # Ensure the word 'json' is in messages for non-Qwen models when json_mode is True to prevent Groq API 400 errors
                has_json_word = False
                for m in messages:
                    if "json" in m.get("content", "").lower():
                        has_json_word = True
                        break
                if not has_json_word:
                    payload_messages = []
                    has_system = False
                    for m in messages:
                        if m.get("role") == "system":
                            has_system = True
                            payload_messages.append({
                                "role": "system",
                                "content": m.get("content", "") + "\n\nNote: Please respond in JSON format."
                            })
                        else:
                            payload_messages.append(m)
                    if not has_system:
                        payload_messages.insert(0, {
                            "role": "system",
                            "content": "Please respond in JSON format."
                        })

            payload = {
                "model": current_model,
                "messages": payload_messages,
                "temperature": temperature,
                "max_tokens": target_max_tokens
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Cutoff think block detection
                    if "<think>" in content and "</think>" not in content:
                        logger.warning("Groq model %s response was cut off inside the thinking block. Trying next model.", current_model)
                        continue
                    
                    # Log token usage
                    usage = data.get("usage", {})
                    if usage:
                        logger.info("Groq API token usage for model %s: prompt=%s, completion=%s, total=%s",
                                    current_model, usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"))
                    return content
                elif resp.status_code == 429:
                    logger.warning("Groq model %s rate limited (429).", current_model)
                    raise RateLimitExceededError(f"Groq rate limit exceeded for {current_model}")
                else:
                    logger.warning("Groq call failed for model %s with status %d: %s", current_model, resp.status_code, resp.text)
                    raise ProviderError(f"Groq API error {resp.status_code}: {resp.text}")
            except (RateLimitExceededError, ProviderError):
                raise
            except Exception as e:
                logger.warning("Groq call failed for model %s with exception: %s", current_model, e)
                # If it's a timeout string representation or specifically a timeout exception
                if "timeout" in str(e).lower():
                    raise CascadeTimeoutError(f"Groq timeout for {current_model}")
                raise ProviderError(f"Groq connection error: {e}")

        return None

    async def transcribe(
        self,
        audio_bytes: bytes,
        file_extension: str,
        timeout: float
    ) -> Optional[str]:
        if not settings.GROQ_API_KEY:
            return None

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        
        # Audio mime mapping helper
        mime_mapping = {
            "ogg": "audio/ogg", "opus": "audio/ogg", "mp3": "audio/mpeg", 
            "m4a": "audio/mp4", "mp4": "audio/mp4", "wav": "audio/wav", 
            "aac": "audio/aac", "flac": "audio/flac"
        }
        mime_type = mime_mapping.get(file_extension.lower().strip(), "audio/ogg")
        filename = f"audio.{file_extension}"
        files = {"file": (filename, audio_bytes, mime_type)}

        client = get_http_client()
        provider_cfg = cascade_settings.get_provider_config(self.provider_name)
        cfg_models = provider_cfg.get("models", {})
        models = [m for m, meta in cfg_models.items() if meta.get("status") == "active" and "whisper" in m.lower()]
        if not models:
            models = ["whisper-large-v3-turbo", "whisper-large-v3"]

        for model in models:
            try:
                resp = await client.post(url, files=files, data={"model": model}, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json().get("text")
                elif resp.status_code == 429:
                    raise RateLimitExceededError(f"Groq rate limit exceeded for {model}")
                else:
                    logger.warning("Groq transcription failed on model %s with status %d: %s", model, resp.status_code, resp.text)
                    raise ProviderError(f"Groq transcription API error {resp.status_code}: {resp.text}")
            except (RateLimitExceededError, ProviderError):
                raise
            except Exception as e:
                logger.warning("Groq transcription failed on model %s with exception: %s", model, e)
                if "timeout" in str(e).lower():
                    raise CascadeTimeoutError(f"Groq transcription timeout for {model}")
                raise ProviderError(f"Groq transcription connection error: {e}")
                
        return None
