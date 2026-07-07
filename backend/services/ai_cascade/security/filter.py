import re
from typing import Optional
from backend.services.ai_cascade.shared.exceptions import SecurityViolationError


class SecurityLayer:
    def __init__(self):
        # Direct prompt injection detection regexes
        self._injection_patterns = [
            re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
            re.compile(r"system\s+prompt\s+bypass", re.IGNORECASE),
            re.compile(r"you\s+must\s+now\s+act\s+as", re.IGNORECASE),
            re.compile(r"developer\s+mode\s+enable", re.IGNORECASE),
        ]

    def validate_prompt(self, prompt: str) -> None:
        """Inspects the rendered prompt for potential security violations or oversized inputs."""
        if len(prompt) > 500000:
            raise SecurityViolationError("Payload size exceeds maximum allowed character threshold of 500,000.")

        for pattern in self._injection_patterns:
            if pattern.search(prompt):
                raise SecurityViolationError("Potential prompt injection attempt detected.")


security_layer = SecurityLayer()


def mask_pii(text: str) -> str:
    if not text:
        return text
    # Mask emails
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    text = re.sub(email_pattern, "[MASKED_EMAIL]", text)
    # Mask phone numbers
    phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\b\d{10,11}\b"
    text = re.sub(phone_pattern, "[MASKED_PHONE]", text)
    return text


def check_prompt_injection(query: str) -> Optional[str]:
    if not query:
        return None
    
    query_lower = query.lower()

    # 1. Direct block escape attempts (XML tags breaking out)
    if "</user_query>" in query_lower or "</retrieved_context>" in query_lower:
        return "Your query was flagged by the safety system as a potential instruction override attempt and cannot be processed."

    # 2. Markdown/Code Block breakout attempts
    if "```" in query:
        return "Your query was flagged by the safety system as a potential instruction override attempt and cannot be processed."

    # 3. System Role Mimicry/Chat Format Hijacking
    mimicry_pattern = r"\b(?:system|instruction|assistant|human|role)\s*:"
    if re.search(mimicry_pattern, query_lower):
        return "Your query was flagged by the safety system as a potential instruction override attempt and cannot be processed."

    # 4. Keyword and Override Phrase matches
    injection_keywords = [
        "ignore all instructions",
        "reveal system instructions",
        "system prompt override",
        "ignore system rules",
        "override prompt",
        "forget system prompt",
        "instead of answering",
        "disregard previous",
        "ignore previous",
        "ignore the above",
        "disregard above",
        "disregard all",
        "new instruction",
        "you are now",
        "act as",
        "ignore rules",
    ]
    if any(keyword in query_lower for keyword in injection_keywords):
        return "Your query was flagged by the safety system as a potential instruction override attempt and cannot be processed."

    return None
