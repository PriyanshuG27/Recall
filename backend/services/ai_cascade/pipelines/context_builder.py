import jinja2
from pathlib import Path
from typing import Any, Dict

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class PromptContextBuilder:
    def __init__(self):
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
            autoescape=False
        )

    def build_prompt(
        self,
        template_name: str,
        variables: Dict[str, Any]
    ) -> str:
        """Loads a Jinja2 template and renders it with the provided variable context."""
        try:
            template = self.env.get_template(template_name)
            return template.render(**variables)
        except jinja2.TemplateNotFound:
            raise ValueError(f"Prompt template '{template_name}' not found under {PROMPTS_DIR}")


prompt_context_builder = PromptContextBuilder()
