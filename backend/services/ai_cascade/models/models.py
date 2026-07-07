from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict

from enum import Enum

class AIState(str, Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    RETRYING = "Retrying"
    FALLBACK = "Fallback"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"


class AITask(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    input_data: Dict[str, Any]
    priority: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    task: AITask
    pipeline: str
    providers: List[str]
    prompt_version: str
    schema_version: str
    retry_policy: Dict[str, Any] = Field(default_factory=dict)
    cache_policy: Dict[str, Any] = Field(default_factory=dict)
    security_policy: Dict[str, Any] = Field(default_factory=dict)
    timeout_policy: Dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    status: AIState = AIState.QUEUED
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    execution_id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    attempts: List[Dict[str, Any]] = Field(default_factory=list)


class PipelineContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    ocr_text: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    embeddings: Optional[List[float]] = None
    retrieved_chunks: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def copy_with(self, **kwargs) -> "PipelineContext":
        return self.model_copy(update=kwargs)

    def with_ocr_text(self, ocr_text: str) -> "PipelineContext":
        return self.copy_with(ocr_text=ocr_text)

    def with_transcript(self, transcript: str) -> "PipelineContext":
        return self.copy_with(transcript=transcript)

    def with_summary(self, summary: str) -> "PipelineContext":
        return self.copy_with(summary=summary)

    def with_embeddings(self, embeddings: List[float]) -> "PipelineContext":
        return self.copy_with(embeddings=embeddings)

    def with_retrieved_chunks(self, retrieved_chunks: List[str]) -> "PipelineContext":
        return self.copy_with(retrieved_chunks=retrieved_chunks)


class BaseAIResult(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provider_used: str
    model_used: str


class SummaryResult(BaseAIResult):
    summary: str
    key_points: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    context_prompt: Optional[str] = None


class InsightResult(BaseAIResult):
    insight: str
    connecting_theme: Optional[str] = None


class QuizResult(BaseAIResult):
    question: str
    options: List[str]
    correct_index: int
    explanation: Optional[str] = None


class OCRResult(BaseAIResult):
    text: str
    confidence: Optional[float] = None


class TranscriptionResult(BaseAIResult):
    transcript: str
    duration_seconds: Optional[float] = None
    segments: List[Dict[str, Any]] = Field(default_factory=list)


class RAGResult(BaseAIResult):
    answer: str
    source_documents: List[Dict[str, Any]] = Field(default_factory=list)

