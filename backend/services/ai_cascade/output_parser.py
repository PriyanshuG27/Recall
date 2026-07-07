import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def strip_thinking(text: str) -> str:
    if not text:
        return ""
    # Remove closed think blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove any unclosed think block (if <think> is still in text)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    # Clean up any stray closing tags
    cleaned = cleaned.replace("</think>", "")
    return cleaned.strip()

def sanitize_json_newlines(s: str) -> str:
    """
    Scans a string, identifies raw newlines inside double-quoted JSON string values,
    and escapes them to '\\n' so it forms a valid JSON block.
    """
    chars = []
    in_string = False
    escaped = False
    for char in s:
        if char == '"' and not escaped:
            in_string = not in_string
        if char == '\\' and in_string:
            escaped = not escaped
        else:
            escaped = False
            
        if char == '\n' and in_string:
            chars.append('\\n')
        else:
            chars.append(char)
    return "".join(chars)

def extract_fields_from_truncated_json(text: str) -> Dict[str, Any]:
    """
    Attempts to extract 'summary', 'tags', and 'context_prompt' from a potentially
    truncated or malformed JSON string when standard json.loads fails.
    """
    res = {}
    
    # 1. Try to parse summary
    summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if summary_match:
        val = summary_match.group(1)
        try:
            val = json.loads(f'"{val}"')
        except Exception:
            val = val.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
        res["summary"] = val.rstrip('\\').strip()
    
    # 2. Try to parse tags
    tags_match = re.search(r'"tags"\s*:\s*\[([^\]]*)', text, re.DOTALL)
    if tags_match:
        tags_str = tags_match.group(1)
        tags = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', tags_str)
        if tags:
            res["tags"] = tags
            
    # 3. Try to parse context_prompt
    context_match = re.search(r'"context_prompt"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if context_match:
        val = context_match.group(1)
        try:
            val = json.loads(f'"{val}"')
        except Exception:
            val = val.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
        res["context_prompt"] = val.rstrip('\\').strip()
        
    return res

def parse_json_response(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = strip_thinking(text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
        cleaned = cleaned.strip()

    cleaned = sanitize_json_newlines(cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Standard JSON parsing failed: %s. Attempting regex recovery.", e)
        
    return extract_fields_from_truncated_json(cleaned)
