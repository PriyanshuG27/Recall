from pydantic import BaseModel, Field, ConfigDict
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
    correct_index: int
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
