from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.providers.registry import provider_registry
from backend.services.ai_cascade.providers.factory import provider_factory
from backend.services.ai_cascade.providers.manager import provider_manager

# Import adapters to expose them to registry and router
from backend.services.ai_cascade.providers.groq import GroqProvider
from backend.services.ai_cascade.providers.gemini import GeminiProvider
from backend.services.ai_cascade.providers.nvidia import NvidiaProvider
from backend.services.ai_cascade.providers.cerebras import CerebrasProvider
from backend.services.ai_cascade.providers.openrouter import OpenRouterProvider
from backend.services.ai_cascade.providers.modal import ModalProvider

# Auto-register adapters at package startup
provider_registry.register("groq", GroqProvider)
provider_registry.register("gemini", GeminiProvider)
provider_registry.register("nvidia", NvidiaProvider)
provider_registry.register("cerebras", CerebrasProvider)
provider_registry.register("openrouter", OpenRouterProvider)
provider_registry.register("modal", ModalProvider)

__all__ = [
    "BaseProvider",
    "ProviderCapability",
    "provider_registry",
    "provider_factory",
    "provider_manager",
    "GroqProvider",
    "GeminiProvider",
    "NvidiaProvider",
    "CerebrasProvider",
    "OpenRouterProvider",
    "ModalProvider",
]
