from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class GraphPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "graph"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return "You are Recall. Generate a semantic graph mapping connections between elements."

    def build_user_prompt(self, context: PipelineContext) -> str:
        return "Generate graph connections."
