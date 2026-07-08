import pytest
import logging
from unittest.mock import MagicMock, patch

from backend.services.ai_cascade.shared.exceptions import OutputValidationError
from backend.services.ai_cascade.validators.registry import QuizValidator, SummaryValidator
from backend.services.ai_cascade.validators.schemas import QuizValidatorModel

# ---------------------------------------------------------------------------
# 1. Markdown Fences & Balanced JSON Extraction Tests
# ---------------------------------------------------------------------------
def test_clean_markdown_fences():
    validator = SummaryValidator()
    
    # Missing newlines
    raw_1 = "```json{\"summary\": \"Test summary\", \"tags\": [], \"key_points\": []}```"
    assert validator.clean_markdown_json(raw_1) == '{"summary": "Test summary", "tags": [], "key_points": []}'
    
    # Mixed whitespace and capitals
    raw_2 = "   ```JSON\n{\"summary\": \"Test summary\", \"tags\": [], \"key_points\": []}\n```   "
    assert validator.clean_markdown_json(raw_2) == '{"summary": "Test summary", "tags": [], "key_points": []}'


def test_outermost_balanced_json_extraction():
    validator = SummaryValidator()

    # Prefix/suffix prose
    raw_1 = "Some explanatory text before JSON.\n\n{\"summary\": \"Test summary\", \"tags\": [], \"key_points\": []}\n\nSome trailer text."
    extracted_1 = validator.extract_json_arrays(raw_1)
    assert extracted_1 == '{"summary": "Test summary", "tags": [], "key_points": []}'

    # Braces inside string values (should not terminate early)
    raw_2 = "{\"summary\": \"This is a value with } closing brace inside\", \"tags\": [], \"key_points\": []}"
    extracted_2 = validator.extract_json_arrays(raw_2)
    assert extracted_2 == raw_2

    # Escaped quotes inside strings
    raw_3 = "{\"summary\": \"Value with \\\"escaped quotes\\\" inside\", \"tags\": [], \"key_points\": []}"
    extracted_3 = validator.extract_json_arrays(raw_3)
    assert extracted_3 == raw_3

    # Nested brackets/arrays
    raw_4 = "{\"summary\": \"Nested arrays check\", \"tags\": [\"a\", \"b\"], \"key_points\": [\"point 1\"]}"
    extracted_4 = validator.extract_json_arrays(raw_4)
    assert extracted_4 == raw_4

    # Unicode characters
    raw_5 = "{\"summary\": \"Unicode check: 🌟 Sparkles\", \"tags\": [], \"key_points\": []}"
    extracted_5 = validator.extract_json_arrays(raw_5)
    assert extracted_5 == raw_5


# ---------------------------------------------------------------------------
# 2. Pydantic Alias Support Tests
# ---------------------------------------------------------------------------
def test_quiz_model_alias_support():
    # Verify that QuizValidatorModel can accept "answer_index" directly via AliasChoices
    data = {
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin"],
        "answer_index": 0
    }
    model = QuizValidatorModel(**data)
    assert model.correct_index == 0


# ---------------------------------------------------------------------------
# 3. Auto-Repair & Default Optional Fields Tests
# ---------------------------------------------------------------------------
def test_summary_validator_auto_repair_defaults():
    validator = SummaryValidator()
    
    # Missing tags and key_points lists entirely
    incomplete = {"summary": "This is a valid summary test length."}
    repaired = validator.auto_repair(incomplete)
    
    assert repaired["tags"] == []
    assert repaired["key_points"] == []
    assert repaired["summary"] == "This is a valid summary test length."


def test_quiz_validator_auto_repair_alias_fallback():
    validator = QuizValidator()
    
    data = {
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin"],
        "answer_index": 1
    }
    repaired = validator.auto_repair(data)
    assert repaired["correct_index"] == 1


# ---------------------------------------------------------------------------
# 4. Required Fields Failure Tests (Deterministic only)
# ---------------------------------------------------------------------------
def test_missing_required_fields_fails():
    validator = QuizValidator()
    
    # Missing required field "question" (should fail validation, not invent question)
    data = {
        "options": ["Paris", "London"],
        "correct_index": 0
    }
    repaired = validator.auto_repair(data)
    
    with pytest.raises(OutputValidationError) as exc:
        validator.validate(repaired)
    assert "Quiz validation failed" in str(exc.value)


# ---------------------------------------------------------------------------
# 5. Telemetry Repair Logging Verification
# ---------------------------------------------------------------------------
def test_repair_telemetry_logs():
    validator = QuizValidator()
    data = {
        "question": "What is the capital of France?",
        "options": ["Paris", "London"],
        "answer_index": 0
    }
    
    with patch("backend.services.ai_cascade.validators.registry.logger.debug") as mock_debug:
        validator.auto_repair(data)
        # Verify that we emit the specific audit repair event with repair type enum
        mock_debug.assert_called_once_with(
            "validator_repair_applied validator=QuizValidator repair=FIELD_ALIAS"
        )
