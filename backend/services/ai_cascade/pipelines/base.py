from abc import ABC, abstractmethod
from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability


class BasePipeline(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the pipeline name matching pipeline configuration keys."""
        pass

    @property
    @abstractmethod
    def required_capabilities(self) -> List[ModelCapability]:
        """Returns the list of capability requirements needed by this pipeline."""
        pass

    @abstractmethod
    def build_system_prompt(self, context: PipelineContext) -> str:
        """Builds the system instructions context for the prompt."""
        pass

    @abstractmethod
    def build_user_prompt(self, context: PipelineContext) -> str:
        """Builds the user payload instructions context for the prompt."""
        pass
