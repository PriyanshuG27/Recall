from enum import Enum
from typing import Set, Dict, Any, List, Optional
from pydantic import BaseModel

class ModelCapability(str, Enum):
    TEXT_GENERATION = "text_generation"
    STRUCTURED_JSON = "structured_json"
    SPEECH_TO_TEXT = "speech_to_text"
    VISION = "vision"

class ModelMetadata(BaseModel):
    model_id: str
    provider_name: str
    capabilities: Set[ModelCapability]
    context_window: int
    max_output_tokens: int
    latency_class: str = "medium"
    is_active: bool = True

    @property
    def max_context_tokens(self) -> int:
        return self.context_window

    @property
    def cost_per_million_input(self) -> float:
        from backend.services.ai_cascade.telemetry.cost_manager import MODEL_PRICING
        return MODEL_PRICING.get(self.model_id, {}).get("input_cost_per_1m", 0.0)

    @property
    def cost_per_million_output(self) -> float:
        from backend.services.ai_cascade.telemetry.cost_manager import MODEL_PRICING
        return MODEL_PRICING.get(self.model_id, {}).get("output_cost_per_1m", 0.0)


class ModelRegistry:
    """Registry tracking available models and capabilities."""
    _models: Dict[str, ModelMetadata] = {}

    @classmethod
    def register_model(cls, meta: ModelMetadata) -> None:
        cls._models[meta.model_id] = meta

    @classmethod
    def get_model(cls, model_id: str) -> ModelMetadata:
        if model_id not in cls._models:
            # Try to match key or raise
            matched_key = None
            for key in cls._models:
                if key in model_id or model_id in key:
                    matched_key = key
                    break
            if not matched_key:
                raise ValueError(f"Model '{model_id}' is not registered.")
            return cls._models[matched_key]
        return cls._models[model_id]

    @classmethod
    def get_models_by_capability(cls, capability: ModelCapability) -> List[ModelMetadata]:
        return [
            m for m in cls._models.values()
            if m.is_active and capability in m.capabilities
        ]

# Pre-populate registry with default models from legacy cascades
DEFAULT_MODELS = [
    # Gemini
    ModelMetadata(
        model_id="gemini-3.1-flash-lite",
        provider_name="gemini",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON, ModelCapability.SPEECH_TO_TEXT, ModelCapability.VISION},
        context_window=1048576,
        max_output_tokens=8192,
        latency_class="low"
    ),
    # Groq Text
    ModelMetadata(
        model_id="openai/gpt-oss-120b",
        provider_name="groq",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON},
        context_window=8192,
        max_output_tokens=2048,
        latency_class="low"
    ),
    ModelMetadata(
        model_id="openai/gpt-oss-20b",
        provider_name="groq",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON},
        context_window=8192,
        max_output_tokens=2048,
        latency_class="low"
    ),
    ModelMetadata(
        model_id="qwen/qwen3-32b",
        provider_name="groq",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON},
        context_window=32768,
        max_output_tokens=2048,
        latency_class="low"
    ),
    # Groq Audio
    ModelMetadata(
        model_id="whisper-large-v3-turbo",
        provider_name="groq",
        capabilities={ModelCapability.SPEECH_TO_TEXT},
        context_window=224288,
        max_output_tokens=0,
        latency_class="low"
    ),
    ModelMetadata(
        model_id="whisper-large-v3",
        provider_name="groq",
        capabilities={ModelCapability.SPEECH_TO_TEXT},
        context_window=224288,
        max_output_tokens=0,
        latency_class="low"
    ),
    # Nvidia NIM
    ModelMetadata(
        model_id="qwen/qwen3-next-80b-a3b",
        provider_name="nvidia",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=16384,
        max_output_tokens=4096,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="deepseek/deepseek-v4-pro",
        provider_name="nvidia",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=8192,
        max_output_tokens=2048,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="nvidia/gpt-oss-120b",
        provider_name="nvidia",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=8192,
        max_output_tokens=2048,
        latency_class="medium"
    ),
    # OpenRouter
    ModelMetadata(
        model_id="openai/gpt-oss-120b:free",
        provider_name="openrouter",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=4096,
        max_output_tokens=1024,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="meta-llama/llama-3.3-70b-instruct:free",
        provider_name="openrouter",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=4096,
        max_output_tokens=1024,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="mistralai/mistral-7b-instruct:free",
        provider_name="openrouter",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=4096,
        max_output_tokens=1024,
        latency_class="medium"
    ),
    # Modal
    ModelMetadata(
        model_id="modal-summary",
        provider_name="modal",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=16384,
        max_output_tokens=2048,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="modal-transcribe",
        provider_name="modal",
        capabilities={ModelCapability.SPEECH_TO_TEXT},
        context_window=224288,
        max_output_tokens=0,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="modal-tags",
        provider_name="modal",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=16384,
        max_output_tokens=2048,
        latency_class="medium"
    ),
    ModelMetadata(
        model_id="modal-rag",
        provider_name="modal",
        capabilities={ModelCapability.TEXT_GENERATION},
        context_window=16384,
        max_output_tokens=2048,
        latency_class="medium"
    ),
    # Cerebras
    ModelMetadata(
        model_id="cerebras/openai/gpt-oss-120b",
        provider_name="cerebras",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_JSON},
        context_window=8192,
        max_output_tokens=2048,
        latency_class="low"
    )
]

for model in DEFAULT_MODELS:
    ModelRegistry.register_model(model)
