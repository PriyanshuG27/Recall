from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class InsightPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "insight"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON]

    def build_system_prompt(self, context: PipelineContext) -> str:
        from backend.services.ai_cascade.prompt_manager import PromptManager
        return PromptManager.get_prompt("insight", "v1")

    def build_user_prompt(self, context: PipelineContext) -> str:
        item_a = context.metadata.get("item_a", {})
        item_b = context.metadata.get("item_b", {})
        days_apart = context.metadata.get("days_apart", 0)
        return (
            f"Item A:\nTitle: {item_a.get('title')}\nSummary: {item_a.get('summary')}\nTags: {item_a.get('tags')}\n\n"
            f"Item B:\nTitle: {item_b.get('title')}\nSummary: {item_b.get('summary')}\nTags: {item_b.get('tags')}\n\n"
            f"Days between saves: {days_apart}"
        )
