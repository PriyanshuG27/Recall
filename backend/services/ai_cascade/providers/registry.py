from typing import Dict, Type
from backend.services.ai_cascade.providers.base import BaseProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, Type[BaseProvider]] = {}

    def register(self, provider_name: str, provider_class: Type[BaseProvider]) -> None:
        """Registers a provider adapter class under a name."""
        self._providers[provider_name.lower()] = provider_class

    def get_provider_class(self, provider_name: str) -> Type[BaseProvider]:
        """Retrieves the registered class for a provider, or raises ValueError if not found."""
        name_lower = provider_name.lower()
        if name_lower not in self._providers:
            raise ValueError(f"Provider '{provider_name}' is not registered in the registry.")
        return self._providers[name_lower]

    def list_providers(self) -> Dict[str, Type[BaseProvider]]:
        """Returns all registered providers."""
        return self._providers.copy()


provider_registry = ProviderRegistry()
