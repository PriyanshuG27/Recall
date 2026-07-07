from typing import Any, Dict
from backend.services.ai_cascade.models import BaseAIResult, SummaryResult


class ResponseComposer:
    def compose_response(self, result: BaseAIResult) -> Dict[str, Any]:
        """
        Translates internal BaseAIResult objects into cleanly structured
        API Response DTOs.
        """
        response = {
            "provider": result.provider_used,
            "model": result.model_used,
            "success": True
        }

        # Format specialized result fields based on types
        if isinstance(result, SummaryResult):
            response.update({
                "summary": result.summary,
                "tags": result.tags,
                "key_points": result.key_points,
                "context_prompt": result.context_prompt
            })
        elif hasattr(result, "transcript"):
            response["transcript"] = getattr(result, "transcript")
        elif hasattr(result, "insights"):
            response["insights"] = getattr(result, "insights")
        elif hasattr(result, "questions"):
            response["questions"] = getattr(result, "questions")
        elif hasattr(result, "text"):
            response["text"] = getattr(result, "text")
        elif hasattr(result, "answer"):
            response["answer"] = getattr(result, "answer")

        return response


response_composer = ResponseComposer()
