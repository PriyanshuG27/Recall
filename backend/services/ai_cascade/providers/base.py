from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ProviderCapability(str, Enum):
    CHAT_COMPLETION = "chat_completion"
    TRANSCRIPTION = "transcription"
    VISION = "vision"


class BaseProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the unique identifier string for this provider."""
        pass

    @property
    @abstractmethod
    def supported_capabilities(self) -> Set[ProviderCapability]:
        """Returns a set of capabilities supported by this provider."""
        pass

    async def initialize(self) -> None:
        """Runs any startup initialization for connection pools/SDKs."""
        pass

    async def shutdown(self) -> None:
        """Cleans up SDK resources and connection pools on shutdown."""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        """Executes a chat completion request and returns the raw string response."""
        pass

    async def transcribe(
        self,
        audio_bytes: bytes,
        file_extension: str,
        timeout: float
    ) -> Optional[str]:
        """Transcribes audio data to text."""
        raise NotImplementedError(f"Transcription is not supported by {self.provider_name}.")
