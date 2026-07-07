from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline
from backend.services.ai_cascade.prompt_manager import PromptManager


class JointSummaryPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "joint_summary"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return PromptManager.get_prompt("joint_summary", "v1")

    def build_user_prompt(self, context: PipelineContext) -> str:
        return context.metadata.get("text", "")
