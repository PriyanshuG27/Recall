import hashlib
import json
from typing import Any, Dict, Optional


class CacheManager:
    def __init__(self):
        # Distinct in-memory caches for Phase 1 MVP
        self._transcription_cache: Dict[str, str] = {}
        self._ocr_cache: Dict[str, str] = {}
        self._llm_response_cache: Dict[str, Dict[str, Any]] = {}

    def _hash_key(self, **kwargs) -> str:
        """Deterministic SHA256 key generation based on input arguments."""
        serialized = json.dumps(kwargs, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_transcription(self, audio_hash: str) -> Optional[str]:
        return self._transcription_cache.get(audio_hash)

    def set_transcription(self, audio_hash: str, text: str) -> None:
        self._transcription_cache[audio_hash] = text

    def get_ocr(self, document_hash: str) -> Optional[str]:
        return self._ocr_cache.get(document_hash)

    def set_ocr(self, document_hash: str, text: str) -> None:
        self._ocr_cache[document_hash] = text

    def get_llm_response(
        self,
        normalized_input: str,
        prompt_version: str,
        pipeline_name: str
    ) -> Optional[Dict[str, Any]]:
        """Checks the cache and returns cached payload dict or None."""
        key = self._hash_key(
            input=normalized_input,
            prompt_version=prompt_version,
            pipeline=pipeline_name
        )
        return self._llm_response_cache.get(key)

    def set_llm_response(
        self,
        normalized_input: str,
        prompt_version: str,
        pipeline_name: str,
        response_data: Dict[str, Any]
    ) -> None:
        """Saves a response payload dict to the response cache."""
        key = self._hash_key(
            input=normalized_input,
            prompt_version=prompt_version,
            pipeline=pipeline_name
        )
        self._llm_response_cache[key] = response_data


cache_manager = CacheManager()
