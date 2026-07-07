import hashlib
import logging
import json
from typing import Optional, Any
from backend.services.redis_client import redis, RedisUnavailableError

logger = logging.getLogger(__name__)

class CacheManager:
    _memory_cache = {}

    @classmethod
    def generate_hash(cls, content: Any) -> str:
        """Generates a 16-character SHA-256 hash prefix for caching keys."""
        if not content:
            return ""
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            try:
                content_bytes = json.dumps(content).encode("utf-8")
            except Exception:
                content_bytes = str(content).encode("utf-8")
        return hashlib.sha256(content_bytes).hexdigest()[:16]

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        try:
            val = await redis.get(key)
            if val is not None:
                return val
        except RedisUnavailableError as re:
            logger.warning("Upstash Redis unavailable during get for key %s: %s. Using memory fallback.", key, re)
        except Exception as e:
            logger.warning("Unexpected error during Redis get for key %s: %s. Using memory fallback.", key, e)
            
        return cls._memory_cache.get(key)

    @classmethod
    async def set(cls, key: str, value: str, ttl: Optional[int] = None) -> bool:
        # In-memory fallback caching
        cls._memory_cache[key] = value
        
        try:
            if ttl:
                await redis.setex(key, ttl, value)
            else:
                await redis.set(key, value)
            return True
        except RedisUnavailableError as re:
            logger.warning("Upstash Redis unavailable during set for key %s: %s.", key, re)
        except Exception as e:
            logger.warning("Unexpected error during Redis set for key %s: %s.", key, e)
            
        return False

    @classmethod
    def _hash_key(cls, **kwargs) -> str:
        """Deterministic SHA256 key generation based on input arguments."""
        serialized = json.dumps(kwargs, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    async def get_transcription(cls, audio_hash: str) -> Optional[str]:
        return await cls.get(f"ai_cascade:transcription:{audio_hash}")

    @classmethod
    async def set_transcription(cls, audio_hash: str, text: str) -> None:
        await cls.set(f"ai_cascade:transcription:{audio_hash}", text)

    @classmethod
    async def get_ocr(cls, document_hash: str) -> Optional[str]:
        return await cls.get(f"ai_cascade:ocr:{document_hash}")

    @classmethod
    async def set_ocr(cls, document_hash: str, text: str) -> None:
        await cls.set(f"ai_cascade:ocr:{document_hash}", text)

    @classmethod
    async def get_llm_response(
        cls,
        normalized_input: str,
        prompt_version: str,
        pipeline_name: str
    ) -> Optional[Any]:
        key = cls._hash_key(
            input=normalized_input,
            prompt_version=prompt_version,
            pipeline=pipeline_name
        )
        val = await cls.get(f"ai_cascade:llm_response:{key}")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return None

    @classmethod
    async def set_llm_response(
        cls,
        normalized_input: str,
        prompt_version: str,
        pipeline_name: str,
        response_data: Any
    ) -> None:
        key = cls._hash_key(
            input=normalized_input,
            prompt_version=prompt_version,
            pipeline=pipeline_name
        )
        await cls.set(f"ai_cascade:llm_response:{key}", json.dumps(response_data), ttl=3600 * 24)
