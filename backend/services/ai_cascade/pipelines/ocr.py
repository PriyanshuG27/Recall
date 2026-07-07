from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class OCRPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "ocr"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.VISION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return "You are Recall. Extract text from the provided image/pdf document."

    def build_user_prompt(self, context: PipelineContext) -> str:
        return "Extract all legible text from this document."
