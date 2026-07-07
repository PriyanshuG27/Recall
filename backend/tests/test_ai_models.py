import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from backend.services.ai_cascade.models import (
    AITask,
    ExecutionPlan,
    ExecutionContext,
    PipelineContext,
    BaseAIResult,
    SummaryResult,
    InsightResult,
    QuizResult,
    OCRResult,
    TranscriptionResult,
    RAGResult,
)
from backend.services.ai_cascade.models import AIState


def test_ai_task_initialization_and_validation():
    # Valid minimal task
    task = AITask(input_data={"text": "hello world"})
    assert isinstance(task.task_id, str)
    assert len(task.task_id) > 0
    assert task.priority == 0
    assert task.metadata == {}
    assert task.input_data == {"text": "hello world"}

    # Valid task with custom fields
    task_custom = AITask(
        task_id="custom-id-123",
        input_data={"data": [1, 2, 3]},
        priority=5,
        metadata={"source": "api"}
    )
    assert task_custom.task_id == "custom-id-123"
    assert task_custom.input_data == {"data": [1, 2, 3]}
    assert task_custom.priority == 5
    assert task_custom.metadata == {"source": "api"}

    # Validation: missing input_data
    with pytest.raises(ValidationError) as exc_info:
        AITask(priority=1)
    assert "input_data" in str(exc_info.value)

    # Validation: invalid type for input_data
    with pytest.raises(ValidationError) as exc_info:
        AITask(input_data="not-a-dict")
    assert "input_data" in str(exc_info.value)

    # Validation: invalid type for priority
    with pytest.raises(ValidationError) as exc_info:
        AITask(input_data={"text": "test"}, priority="high")
    assert "priority" in str(exc_info.value)


def test_ai_task_serialization():
    task = AITask(
        task_id="serialization-test",
        input_data={"query": "test query"},
        priority=3,
        metadata={"user_id": 42}
    )
    dumped = task.model_dump()
    assert dumped == {
        "task_id": "serialization-test",
        "input_data": {"query": "test query"},
        "priority": 3,
        "metadata": {"user_id": 42}
    }

    # JSON serialization and deserialization
    json_str = task.model_dump_json()
    loaded = AITask.model_validate_json(json_str)
    assert loaded.task_id == task.task_id
    assert loaded.input_data == task.input_data
    assert loaded.priority == task.priority
    assert loaded.metadata == task.metadata


def test_execution_plan_initialization_and_validation():
    task = AITask(input_data={"doc": "content"})
    
    # Valid minimal execution plan
    plan = ExecutionPlan(
        task=task,
        pipeline="summary_generation",
        providers=["gemini", "groq"],
        prompt_version="v1.0",
        schema_version="1.0"
    )
    assert plan.task == task
    assert plan.pipeline == "summary_generation"
    assert plan.providers == ["gemini", "groq"]
    assert plan.prompt_version == "v1.0"
    assert plan.schema_version == "1.0"
    assert plan.retry_policy == {}
    assert plan.cache_policy == {}
    assert plan.security_policy == {}
    assert plan.timeout_policy == {}

    # Custom policy fields
    plan_custom = ExecutionPlan(
        task=task,
        pipeline="ocr",
        providers=["modal"],
        prompt_version="v2",
        schema_version="2",
        retry_policy={"max_retries": 3, "backoff": 2.0},
        cache_policy={"ttl_seconds": 3600},
        security_policy={"mask_pii": True},
        timeout_policy={"request_timeout": 30.0}
    )
    assert plan_custom.retry_policy == {"max_retries": 3, "backoff": 2.0}
    assert plan_custom.cache_policy == {"ttl_seconds": 3600}
    assert plan_custom.security_policy == {"mask_pii": True}
    assert plan_custom.timeout_policy == {"request_timeout": 30.0}

    # Validation: missing required fields
    with pytest.raises(ValidationError) as exc_info:
        ExecutionPlan(task=task, pipeline="summary_generation")
    assert "providers" in str(exc_info.value)
    assert "prompt_version" in str(exc_info.value)
    assert "schema_version" in str(exc_info.value)

    # Validation: invalid type for task
    with pytest.raises(ValidationError) as exc_info:
        ExecutionPlan(
            task="not-a-task-object",
            pipeline="summary_generation",
            providers=["groq"],
            prompt_version="v1",
            schema_version="1"
        )
    assert "task" in str(exc_info.value)


def test_execution_plan_serialization():
    task = AITask(task_id="t1", input_data={"text": "hi"})
    plan = ExecutionPlan(
        task=task,
        pipeline="test_pipe",
        providers=["cerebras"],
        prompt_version="v1",
        schema_version="1.0",
        retry_policy={"retries": 1}
    )
    dumped = plan.model_dump()
    assert dumped["task"]["task_id"] == "t1"
    assert dumped["pipeline"] == "test_pipe"
    assert dumped["providers"] == ["cerebras"]
    assert dumped["retry_policy"] == {"retries": 1}

    json_str = plan.model_dump_json()
    loaded = ExecutionPlan.model_validate_json(json_str)
    assert loaded.task.task_id == "t1"
    assert loaded.pipeline == "test_pipe"
    assert loaded.providers == ["cerebras"]
    assert loaded.retry_policy == {"retries": 1}


def test_execution_context_initialization_and_validation():
    # Minimal validation
    context = ExecutionContext()
    assert context.status == AIState.QUEUED
    assert isinstance(context.request_id, str)
    assert len(context.request_id) > 0
    assert isinstance(context.execution_id, str)
    assert len(context.execution_id) > 0
    assert context.started_at is None
    assert context.finished_at is None

    # Custom context
    started = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 7, 7, 10, 5, 0, tzinfo=timezone.utc)
    context_custom = ExecutionContext(
        status=AIState.RUNNING,
        request_id="req-123",
        execution_id="exec-456",
        started_at=started,
        finished_at=finished
    )
    assert context_custom.status == AIState.RUNNING
    assert context_custom.request_id == "req-123"
    assert context_custom.execution_id == "exec-456"
    assert context_custom.started_at == started
    assert context_custom.finished_at == finished

    # Validation: invalid AIState value
    with pytest.raises(ValidationError) as exc_info:
        ExecutionContext(status="INVALID_STATE")
    assert "status" in str(exc_info.value)

    # Validation: invalid started_at type
    with pytest.raises(ValidationError) as exc_info:
        ExecutionContext(started_at="yesterday")
    assert "started_at" in str(exc_info.value)


def test_execution_context_serialization():
    started = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    context = ExecutionContext(
        status=AIState.SUCCEEDED,
        request_id="req-abc",
        execution_id="exec-xyz",
        started_at=started
    )
    
    json_str = context.model_dump_json()
    loaded = ExecutionContext.model_validate_json(json_str)
    assert loaded.status == AIState.SUCCEEDED
    assert loaded.request_id == "req-abc"
    assert loaded.execution_id == "exec-xyz"
    # Datetimes parsed should match
    assert loaded.started_at == started


def test_base_ai_result_initialization_and_validation():
    # Valid minimal result
    res = BaseAIResult(provider_used="gemini", model_used="gemini-3.1-flash-lite")
    assert res.provider_used == "gemini"
    assert res.model_used == "gemini-3.1-flash-lite"
    assert res.metadata == {}

    # Validation: missing provider_used
    with pytest.raises(ValidationError) as exc_info:
        BaseAIResult(model_used="gpt-4")
    assert "provider_used" in str(exc_info.value)


def test_summary_result_initialization_and_validation():
    # Valid summary result
    res = SummaryResult(
        provider_used="nvidia",
        model_used="qwen3-next-80b",
        summary="This is a summary of the transcript.",
        key_points=["Point 1", "Point 2"],
        metadata={"token_count": 150}
    )
    assert res.provider_used == "nvidia"
    assert res.model_used == "qwen3-next-80b"
    assert res.summary == "This is a summary of the transcript."
    assert res.key_points == ["Point 1", "Point 2"]
    assert res.metadata == {"token_count": 150}

    # Verify default key_points is empty list
    res_minimal = SummaryResult(
        provider_used="openrouter",
        model_used="llama-3",
        summary="Short summary."
    )
    assert res_minimal.key_points == []

    # Verify subclassing
    assert isinstance(res_minimal, BaseAIResult)

    # Validation: missing summary
    with pytest.raises(ValidationError) as exc_info:
        SummaryResult(
            provider_used="openrouter",
            model_used="llama-3"
        )
    assert "summary" in str(exc_info.value)


def test_summary_result_serialization():
    res = SummaryResult(
        provider_used="groq",
        model_used="whisper-large-v3",
        summary="Spoken words.",
        key_points=["hello", "world"],
        tags=["speech"],
        context_prompt="System prompt context"
    )
    dumped = res.model_dump()
    assert dumped["provider_used"] == "groq"
    assert dumped["summary"] == "Spoken words."
    assert dumped["key_points"] == ["hello", "world"]
    assert dumped["tags"] == ["speech"]
    assert dumped["context_prompt"] == "System prompt context"

    json_str = res.model_dump_json()
    loaded = SummaryResult.model_validate_json(json_str)
    assert loaded.provider_used == "groq"
    assert loaded.summary == "Spoken words."
    assert loaded.key_points == ["hello", "world"]
    assert loaded.tags == ["speech"]
    assert loaded.context_prompt == "System prompt context"


def test_pipeline_context_immutability_and_helpers():
    context = PipelineContext(ocr_text="scanned doc text")
    assert context.ocr_text == "scanned doc text"
    assert context.transcript is None
    assert context.summary is None

    # Test frozen/immutability
    try:
        context.ocr_text = "new ocr"
    except (ValidationError, AttributeError):
        # Successfully prevented mutation
        pass
    else:
        pytest.fail("PipelineContext is not frozen")

    # Test helper transitions
    c2 = context.with_transcript("transcribed voice")
    assert c2.ocr_text == "scanned doc text"
    assert c2.transcript == "transcribed voice"
    assert context.transcript is None  # original is unmodified

    c3 = c2.with_summary("the summary").with_embeddings([0.1, 0.2]).with_retrieved_chunks(["chunk1"])
    assert c3.summary == "the summary"
    assert c3.embeddings == [0.1, 0.2]
    assert c3.retrieved_chunks == ["chunk1"]


def test_typed_results_validation():
    # InsightResult
    insight = InsightResult(
        provider_used="nvidia",
        model_used="qwen",
        insight="This is a test insight connecting theme A and B.",
        connecting_theme="Theme A & B"
    )
    assert insight.provider_used == "nvidia"
    assert insight.insight == "This is a test insight connecting theme A and B."

    # QuizResult
    quiz = QuizResult(
        provider_used="gemini",
        model_used="gemini-3.1",
        question="What is the primary language used in this project?",
        options=["Python", "JavaScript", "Go", "Rust"],
        correct_index=0,
        explanation="Python is the primary language used for the backend."
    )
    assert quiz.provider_used == "gemini"
    assert quiz.question == "What is the primary language used in this project?"
    assert quiz.correct_index == 0

    # OCRResult
    ocr = OCRResult(
        provider_used="paddle",
        model_used="ocr-v4",
        text="Recognized characters",
        confidence=0.98
    )
    assert ocr.text == "Recognized characters"
    assert ocr.confidence == 0.98

    # TranscriptionResult
    trans = TranscriptionResult(
        provider_used="groq",
        model_used="whisper",
        transcript="some voice text",
        duration_seconds=120.5,
        segments=[{"start": 0, "end": 10, "text": "some"}]
    )
    assert trans.transcript == "some voice text"
    assert trans.duration_seconds == 120.5
    assert len(trans.segments) == 1

    # RAGResult
    rag = RAGResult(
        provider_used="cerebras",
        model_used="gpt-oss",
        answer="Paris is the capital of France.",
        source_documents=[{"id": 1, "text": "Paris is France's capital."}]
    )
    assert rag.answer == "Paris is the capital of France."
    assert len(rag.source_documents) == 1

