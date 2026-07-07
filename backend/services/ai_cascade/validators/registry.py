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
    TranscriptionValidatorModel
)

class SummaryValidator(BaseValidator):
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

class QuizValidator(BaseValidator):
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


class ValidatorRegistry:
    _registry: Dict[str, Type[BaseValidator]] = {
        "summary": SummaryValidator,
        "rag": RAGValidator,
        "quiz": QuizValidator,
        "ocr": OCRValidator,
        "insight": InsightValidator,
        "transcription": TranscriptionValidator
    }

    @classmethod
    def get_validator(cls, pipeline_name: str) -> BaseValidator:
        validator_cls = cls._registry.get(pipeline_name)
        if not validator_cls:
            raise ValueError(f"No validator registered for pipeline: {pipeline_name}")
        return validator_cls()
