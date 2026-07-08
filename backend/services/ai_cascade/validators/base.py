import abc
import json
import logging
import re
from typing import Any, Dict
from backend.services.ai_cascade.shared.exceptions import OutputValidationError

logger = logging.getLogger(__name__)

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
        Robustly extracts the outermost balanced JSON block ({...} or [...]) from text.
        Tracks brace/bracket depth, ignoring boundaries inside string literals (with escape logic).
        """
        if not raw_text:
            return ""
            
        start_idx = -1
        brace_char = None
        close_char = None
        
        # Find first '{' or '['
        for i, char in enumerate(raw_text):
            if char in ('{', '['):
                start_idx = i
                brace_char = char
                close_char = '}' if char == '{' else ']'
                break
                
        if start_idx == -1:
            return raw_text
            
        depth = 0
        in_string = False
        escape = False
        
        for i in range(start_idx, len(raw_text)):
            char = raw_text[i]
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == brace_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1
                    if depth == 0:
                        return raw_text[start_idx:i+1]
                         
        return raw_text[start_idx:]

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

    def auto_repair(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies deterministic structural repairs (e.g. mapping aliases or initializing collections).
        Overridden by subclasses for validator-specific repairs.
        Never infers missing semantic values.
        """
        return data

    def parse_and_validate(self, raw_text: str) -> Dict[str, Any]:
        """
        Production entry point: cleans, extracts, parses, repairs, and validates output.
        """
        parsed = self.parse_json(raw_text)
        repaired = self.auto_repair(parsed)
        self.validate(repaired)
        return repaired
