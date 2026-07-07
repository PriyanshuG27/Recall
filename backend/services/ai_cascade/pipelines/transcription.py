from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline


class TranscriptionPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "transcription"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.SPEECH_TO_TEXT]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return "You are Recall. Precisely transcribe the provided speech."

    def build_user_prompt(self, context: PipelineContext) -> str:
        return "Transcribe the audio precisely."
