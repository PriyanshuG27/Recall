import asyncio
import random
import logging
from typing import List, Dict, Any
from backend.services.ai_cascade.shared.exceptions import (
    CascadeTimeoutError,
    RateLimitExceededError,
    ProviderError
)

logger = logging.getLogger(__name__)

class RetryEngine:
    async def execute_with_retry(
        self,
        provider,
        messages: List[Dict[str, str]],
        model: str,
        timeout: float,
        retries: int = 1,
        backoff_factor: float = 2.0,
        min_delay: float = 1.0,
        jitter: float = 0.5,
        request_id: str | None = None,
        capability: str = "text_generation",
        extra_args: dict | None = None
    ) -> str:
        """
        Executes a provider chat completion, caption_image, or transcribe with retries.
        Handles HTTP 429 RateLimitExceededError specifically to sleep/cooldown.
        """
        attempt = 0
        extra_args = extra_args or {}
        while True:
            try:
                if capability == "vision" or capability == "ocr":
                    response = await provider.caption_image(
                        image_bytes=extra_args.get("image_bytes"),
                        mime_type=extra_args.get("mime_type", "image/jpeg"),
                        timeout=timeout
                    )
                elif capability == "speech_to_text" or capability == "transcribe":
                    response = await provider.transcribe(
                        audio_bytes=extra_args.get("audio_bytes"),
                        file_extension=extra_args.get("file_extension", "ogg"),
                        timeout=timeout
                    )
                else:
                    response = await provider.chat_completion(
                        messages=messages,
                        temperature=0.7,
                        timeout=timeout,
                        model=model,
                        json_mode=True
                    )
                if response is not None:
                    return response
                raise ProviderError("Provider returned empty completion.")
            except (CascadeTimeoutError, ProviderError) as exc:
                if attempt >= retries:
                    raise exc
                
                is_rate_limit = isinstance(exc, RateLimitExceededError)
                if is_rate_limit:
                    delay = 5.0
                    logger.warning("Rate limit (HTTP 429) hit on provider %s. Applying rate-limit backoff of %0.2fs", provider.__class__.__name__, delay)
                else:
                    delay = min_delay * (backoff_factor ** attempt) + random.uniform(0, jitter)
                    logger.info("Temporary failure on provider %s: %s. Retrying attempt %d/%d in %0.2fs...", provider.__class__.__name__, exc, attempt + 1, retries, delay)
                
                from backend.services.ai_cascade.events.event_bus import event_bus, RetryAttempted
                await event_bus.publish(RetryAttempted(
                    request_id=request_id,
                    provider=provider.__class__.__name__.lower().replace("provider", ""),
                    model=model,
                    attempt_num=attempt + 1,
                    backoff_seconds=delay
                ))
                
                await asyncio.sleep(delay)
                attempt += 1
