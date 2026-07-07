from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class QuizPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "quiz"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return "You are a precise quiz generator. Output ONLY a valid JSON object matching the requested schema."

    def build_user_prompt(self, context: PipelineContext) -> str:
        from backend.services.ai_cascade.prompt_manager import PromptManager
        prompt_template = PromptManager.get_prompt("quiz", "v1")
        transcript = context.transcript or context.metadata.get("text", "")
        return f"{prompt_template}\n\nContent:\n{transcript[:2000]}"
