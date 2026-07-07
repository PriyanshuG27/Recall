import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class PromptManager:
    _cached_prompts: Dict[str, str] = {}
    
    @classmethod
    def get_prompt(cls, name: str, version: str = "v1") -> str:
        key = f"{name}_{version}"
        if key in cls._cached_prompts:
            return cls._cached_prompts[key]
            
        # Locate the prompts directory relative to this file
        dir_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(dir_path, "prompts", f"{name}_{version}.txt")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                cls._cached_prompts[key] = content
                return content
        except Exception as e:
            logger.error("Failed to load prompt %s version %s: %s", name, version, e)
            raise FileNotFoundError(f"Prompt template '{file_path}' not found.") from e
