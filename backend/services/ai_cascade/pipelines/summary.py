from typing import List
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.registry.model_registry import ModelCapability
from backend.services.ai_cascade.pipelines.base import BasePipeline
from backend.services.ai_cascade.pipelines.context_builder import prompt_context_builder

# Mood definitions from the legacy spec for context question prompting
MOODS = {
    "curiosity": {
        "description": "Ask about what specific detail in the content grabbed the user's attention.",
        "example": "This caught my eye — what made you save Kobe's daily practice routine today?"
    },
    "friction": {
        "description": "Ask if they agree with the author, or if they have doubts/conflicting thoughts about it.",
        "example": "Is this something you fully agree with, or do you have some doubts about their approach?"
    },
    "future": {
        "description": "Ask how they plan to apply or reference this content in the future.",
        "example": "What are you planning to build or change using this guide?"
    },
    "timing": {
        "description": "Ask about the situational context or trigger that led them to save it right now.",
        "example": "What was happening in your workday when you felt the need to save this?"
    }
}


class SummaryPipeline(BasePipeline):
    @property
    def name(self) -> str:
        return "summary"

    @property
    def required_capabilities(self) -> List[ModelCapability]:
        return [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON]

    def build_system_prompt(self, context: PipelineContext) -> str:
        return "You are Recall, a smart personal assistant designed to analyze transcripts and extract structure."

    def build_user_prompt(self, context: PipelineContext) -> str:
        mood_category = context.metadata.get("mood_category")
        mood_instruction = ""
        if mood_category and mood_category in MOODS:
            mood_info = MOODS[mood_category]
            mood_instruction = (
                f"You MUST generate the 'context_prompt' question strictly matching the following angle/mood:\n"
                f"Mood Category: {mood_category}\n"
                f"Angle/Definition: {mood_info['description']}\n"
                f"Example style: {mood_info['example']}\n"
                f"Ensure the generated question is conversational, exactly 1 sentence, and directly tailored to the saved content."
            )

        return prompt_context_builder.build_prompt(
            "summary_v1.jinja",
            {
                "transcript": context.transcript or "",
                "mood_instruction": mood_instruction
            }
        )
