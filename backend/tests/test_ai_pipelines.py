import pytest
from backend.services.ai_cascade.models import PipelineContext
from backend.services.ai_cascade.pipelines import (
    prompt_context_builder,
    SummaryPipeline,
    RAGPipeline,
    QuizPipeline,
    OCRPipeline,
    InsightPipeline,
)
from backend.services.ai_cascade.registry.model_registry import ModelCapability


def test_prompt_context_builder_rendering():
    # Render summary_v1 template
    rendered = prompt_context_builder.build_prompt(
        "summary_v1.jinja",
        {"transcript": "This is a raw recording transcript."}
    )
    assert "This is a raw recording transcript." in rendered
    assert "Format your output strictly as a JSON object" in rendered

    # Raise on missing template
    with pytest.raises(ValueError):
        prompt_context_builder.build_prompt("nonexistent.jinja", {})


def test_summary_pipeline_generation():
    pipe = SummaryPipeline()
    assert pipe.name == "summary"
    assert ModelCapability.TEXT_GENERATION in pipe.required_capabilities
    assert ModelCapability.STRUCTURED_JSON in pipe.required_capabilities

    context = PipelineContext(transcript="Meeting transcript content")
    system_prompt = pipe.build_system_prompt(context)
    user_prompt = pipe.build_user_prompt(context)

    assert "smart personal assistant" in system_prompt
    assert "Meeting transcript content" in user_prompt


def test_stubs_pipelines():
    # RAG Pipeline
    rag = RAGPipeline()
    assert rag.name == "rag"
    c_rag = PipelineContext(retrieved_chunks=["chunk A", "chunk B"])
    user_rag = rag.build_user_prompt(c_rag)
    assert "chunk A" in user_rag
    assert "chunk B" in user_rag

    # Quiz Pipeline
    quiz = QuizPipeline()
    assert quiz.name == "quiz"
    c_quiz = PipelineContext(transcript="history facts")
    user_quiz = quiz.build_user_prompt(c_quiz)
    assert "history facts" in user_quiz

    # OCR Pipeline
    ocr = OCRPipeline()
    assert ocr.name == "ocr"
    c_ocr = PipelineContext()
    assert "legible text" in ocr.build_user_prompt(c_ocr)

    # Insight Pipeline
    insight = InsightPipeline()
    assert insight.name == "insight"
    c_insight = PipelineContext(metadata={
        "item_a": {"title": "A", "summary": "fact A", "tags": []},
        "item_b": {"title": "B", "summary": "fact B", "tags": []},
        "days_between": 0
    })
    user_insight = insight.build_user_prompt(c_insight)
    assert "fact A" in user_insight
    assert "fact B" in user_insight
