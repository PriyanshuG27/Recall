from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline
from backend.services.ai_cascade.prompt_manager import PromptManager


class GenerateContextQuestionPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "generate_context_question"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return PromptManager.get_prompt("generate_question", "v1")

    def build_user_prompt(self, context: PipelineContext) -> str:
        title = context.metadata.get("title", "")
        summary = context.metadata.get("summary", "")
        return f"Title: {title}\nSummary: {summary}"
