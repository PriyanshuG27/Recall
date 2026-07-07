import abc
import json
import re
from typing import Any, Dict
from backend.services.ai_cascade.shared.exceptions import OutputValidationError

class BaseValidator(abc.ABC):
    @abc.abstractmethod
    def validate(self, output: Dict[str, Any]) -> bool:
        """
        Validate the dictionary output against specific schemas or heuristics.
        Returns True if valid, raises OutputValidationError or returns False if invalid.
        """
        pass

    def clean_markdown_json(self, raw_text: str) -> str:
        """
        Strips markdown code ticks and whitespace from output text.
        """
        if not raw_text:
            return ""
        text = raw_text.strip()
        # Remove ```json ... ``` blocks
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def extract_json_arrays(self, raw_text: str) -> str:
        """
        Regex heuristic recovery to find the first JSON object or array.
        """
        if not raw_text:
            return ""
        # Match from first { to last }
        match_obj = re.search(r"(\{.*\})", raw_text, re.DOTALL)
        if match_obj:
            return match_obj.group(1)
        # Match from first [ to last ]
        match_arr = re.search(r"(\[.*\])", raw_text, re.DOTALL)
        if match_arr:
            return match_arr.group(1)
        return raw_text

    def parse_json(self, raw_text: str) -> Dict[str, Any]:
        """
        Cleans and parses raw JSON response text.
        Raises OutputValidationError if parsing fails.
        """
        from backend.services.ai_cascade.config import settings
        if not settings.enable_repair:
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError as e:
                raise OutputValidationError(f"Failed to parse JSON (repair disabled): {e}")

        cleaned = self.clean_markdown_json(raw_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try heuristic extraction
            extracted = self.extract_json_arrays(cleaned)
            try:
                return json.loads(extracted)
            except json.JSONDecodeError as e:
                raise OutputValidationError(f"Failed to parse JSON: {e}")
