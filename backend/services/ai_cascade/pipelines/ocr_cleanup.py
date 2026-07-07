from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline
from backend.services.ai_cascade.prompt_manager import PromptManager


class OCRCleanupPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "ocr_cleanup"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return PromptManager.get_prompt("ocr_cleanup", "v1")

    def build_user_prompt(self, context: PipelineContext) -> str:
        ocr_text = context.metadata.get("ocr_text", "")
        return f"Raw OCR text:\n{ocr_text}"
