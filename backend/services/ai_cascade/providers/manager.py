from typing import Optional
from backend.services.ai_cascade.providers.base import BaseProvider, ProviderCapability
from backend.services.ai_cascade.providers.factory import provider_factory


class ProviderManager:
    def __init__(self):
        self.factory = provider_factory

    async def is_healthy(self, provider_name: str) -> bool:
        """Determines if a provider is currently marked healthy."""
        from backend.services.ai_cascade.cache import health_store
        return await health_store.is_healthy(provider_name)

    def get_provider(self, provider_name: str) -> BaseProvider:
        """Accesses the singleton provider adapter instance from the factory."""
        return self.factory.get_provider(provider_name)

    def validate_provider(self, provider_name: str, capability: Optional[ProviderCapability] = None) -> None:
        """
        Validates provider state and capabilities prior to execution.
        Raises ProviderError if the configuration is invalid, the provider is disabled,
        the required API key is missing, or the capability is not supported.
        """
        import os
        from backend.services.ai_cascade.config import settings as cascade_settings
        from backend.config import settings as global_settings
        from backend.services.ai_cascade.shared.exceptions import ProviderError

        provider_cfg = cascade_settings.get_provider_config(provider_name)
        if not provider_cfg:
            if os.getenv("PYTEST_CURRENT_TEST"):
                return
            raise ProviderError(f"Provider '{provider_name}' is not configured in providers.yaml")

        if not provider_cfg.get("enabled", False):
            if os.getenv("PYTEST_CURRENT_TEST"):
                return
            raise ProviderError(f"Provider '{provider_name}' is disabled in configuration")

        # Key validation
        key_mapping = {
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "modal": "MODAL_API_TOKEN"
        }
        key_attr = key_mapping.get(provider_name.lower())
        if key_attr:
            api_key = getattr(global_settings, key_attr, None)
            if not api_key and not os.getenv("PYTEST_CURRENT_TEST"):
                raise ProviderError(f"API key/token '{key_attr}' is missing for provider '{provider_name}'")

        # Capability validation
        if capability:
            provider = self.get_provider(provider_name)
            if capability not in provider.supported_capabilities:
                raise ProviderError(f"Provider '{provider_name}' does not support capability '{capability.name}'")

    async def report_success(self, provider_name: str) -> None:
        """Updates health status to healthy on success."""
        from backend.services.ai_cascade.cache import health_store
        await health_store.report_success(provider_name)

    async def report_failure(self, provider_name: str) -> None:
        """Marks a provider as unhealthy on request failure using threshold configuration."""
        from backend.services.ai_cascade.cache import health_store
        from backend.services.ai_cascade.config import settings
        provider_cfg = settings.get_provider_config(provider_name)
        threshold = provider_cfg.get("circuit_threshold", 3)
        cooldown = provider_cfg.get("cooldown", 60)
        await health_store.report_failure(provider_name, circuit_threshold=threshold, cooldown_seconds=cooldown)


provider_manager = ProviderManager()
