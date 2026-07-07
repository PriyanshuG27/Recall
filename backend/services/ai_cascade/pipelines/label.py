from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class LabelPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "label"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return (
            "You are a precise classifier. What single theme connects these items? "
            "Answer in 4 words or less. Do not write anything else. Keep your answer brief and descriptive."
        )

    def build_user_prompt(self, context: PipelineContext) -> str:
        text = context.metadata.get("text", "")
        return f"Summaries of items:\n\n{text}"
