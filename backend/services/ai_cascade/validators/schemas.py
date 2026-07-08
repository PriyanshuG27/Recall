from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from typing import List, Optional, Dict, Any

class SummaryValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = Field(..., min_length=5)
    tags: List[str] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)
    context_prompt: Optional[str] = None

class RAGValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str = Field(..., min_length=1)
    context_used: List[int] = Field(default_factory=list)

class QuizValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = Field(..., min_length=5)
    options: List[str] = Field(..., min_length=2)
    correct_index: int = Field(..., validation_alias=AliasChoices("correct_index", "answer_index"))
    explanation: Optional[str] = None

class OCRValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0)

class InsightValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    insight: str = Field(..., min_length=5)
    connecting_theme: Optional[str] = None

class TranscriptionValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    transcript: str = Field(..., min_length=1)
    duration_seconds: Optional[float] = None
    segments: List[Dict[str, Any]] = Field(default_factory=list)


class LabelValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = Field(..., min_length=1)


class OnboardingValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)


class OCRCleanupValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    urls: List[str] = Field(default_factory=list)
    is_only_links: bool = False


class SanitizeTranscriptValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    transcript: str = Field(..., min_length=1)


class GenerateContextQuestionValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    context_prompt: str = Field(..., min_length=1)


class JointSummaryValidatorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    context_prompt: Optional[str] = None

