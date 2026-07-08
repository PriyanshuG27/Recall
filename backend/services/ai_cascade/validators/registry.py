from typing import Any, Dict, Type
from pydantic import ValidationError
from backend.services.ai_cascade.shared.exceptions import OutputValidationError
from backend.services.ai_cascade.validators.base import BaseValidator
from backend.services.ai_cascade.validators.schemas import (
    SummaryValidatorModel,
    RAGValidatorModel,
    QuizValidatorModel,
    OCRValidatorModel,
    InsightValidatorModel,
    TranscriptionValidatorModel,
    LabelValidatorModel,
    OnboardingValidatorModel,
    OCRCleanupValidatorModel,
    SanitizeTranscriptValidatorModel,
    GenerateContextQuestionValidatorModel,
    JointSummaryValidatorModel
)
import re
import logging

logger = logging.getLogger(__name__)

class SummaryValidator(BaseValidator):
    def auto_repair(self, data: Dict[str, Any]) -> Dict[str, Any]:
        repaired = False
        if "tags" not in data or data["tags"] is None:
            data["tags"] = []
            repaired = True
        if "key_points" not in data or data["key_points"] is None:
            data["key_points"] = []
            repaired = True
        if repaired:
            logger.debug("validator_repair_applied validator=SummaryValidator repair=DEFAULT_OPTIONAL")
        return data

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            SummaryValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Summary validation failed: {e}")

class RAGValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"answer": raw_text.strip(), "context_used": []}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            RAGValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"RAG validation failed: {e}")

class GraphRAGValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"answer": raw_text.strip(), "context_used": []}

    def validate(self, output: Dict[str, Any]) -> bool:
        answer = output.get("answer") or ""
        banned_patterns = [
            r"you seem interested in", r"you have a passion for",
            r"this might suggest", r"it's possible that", r"perhaps you",
            r"your journey", r"your growth", r"your path"
        ]
        res_lower = answer.lower()
        if any(re.search(pat, res_lower) for pat in banned_patterns):
            raise OutputValidationError(f"Graph RAG answer rejected due to banned phrases: {answer}")
        return True

class QuizValidator(BaseValidator):
    def auto_repair(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "answer_index" in data and "correct_index" not in data:
            data["correct_index"] = data["answer_index"]
            logger.debug("validator_repair_applied validator=QuizValidator repair=FIELD_ALIAS")
        return data

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            QuizValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Quiz validation failed: {e}")

class OCRValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"text": raw_text.strip(), "confidence": 1.0}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            OCRValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"OCR validation failed: {e}")

class InsightValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"insight": raw_text.strip()}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            InsightValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Insight validation failed: {e}")


class TranscriptionValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"transcript": raw_text.strip()}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            TranscriptionValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Transcription validation failed: {e}")


class LabelValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"label": raw_text.strip()}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            LabelValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Label validation failed: {e}")


class OnboardingValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"summary": raw_text.strip(), "tags": []}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            OnboardingValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"Onboarding validation failed: {e}")


class OCRCleanupValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            parsed = super().parse_json(raw_text)
            urls = parsed.get("urls") or []
            is_only_links = bool(parsed.get("is_only_links", False))
            return {"urls": urls, "is_only_links": is_only_links}
        except Exception:
            # Fallback parsing
            urls = re.findall(r"https?://[^\s]+", raw_text)
            return {"urls": urls, "is_only_links": False}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            OCRCleanupValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"OCRCleanup validation failed: {e}")


class SanitizeTranscriptValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"transcript": raw_text.strip()}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            SanitizeTranscriptValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"SanitizeTranscript validation failed: {e}")


class GenerateContextQuestionValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"context_prompt": raw_text.strip()}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            GenerateContextQuestionValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"GenerateContextQuestion validation failed: {e}")


class JointSummaryValidator(BaseValidator):
    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        try:
            return super().parse_json(raw_text)
        except Exception:
            return {"title": "Related Items", "summary": raw_text.strip(), "context_prompt": None}

    def validate(self, output: Dict[str, Any]) -> bool:
        try:
            JointSummaryValidatorModel(**output)
            return True
        except (ValidationError, TypeError) as e:
            raise OutputValidationError(f"JointSummary validation failed: {e}")


class ValidatorRegistry:
    _registry: Dict[str, Type[BaseValidator]] = {
        "summary": SummaryValidator,
        "rag": RAGValidator,
        "quiz": QuizValidator,
        "ocr": OCRValidator,
        "insight": InsightValidator,
        "transcription": TranscriptionValidator,
        "graph": GraphRAGValidator,
        "label": LabelValidator,
        "onboarding": OnboardingValidator,
        "ocr_cleanup": OCRCleanupValidator,
        "sanitize_transcript": SanitizeTranscriptValidator,
        "generate_context_question": GenerateContextQuestionValidator,
        "joint_summary": JointSummaryValidator
    }

    @classmethod
    def get_validator(cls, pipeline_name: str) -> BaseValidator:
        validator_cls = cls._registry.get(pipeline_name)
        if not validator_cls:
            raise ValueError(f"No validator registered for pipeline: {pipeline_name}")
        return validator_cls()
