from typing import Dict
from backend.services.ai_cascade.providers.base import BaseProvider
from backend.services.ai_cascade.providers.registry import provider_registry


class ProviderFactory:
    def __init__(self):
        self._instances: Dict[str, BaseProvider] = {}

    def get_provider(self, provider_name: str) -> BaseProvider:
        """Retrieves or instantiates a cached singleton instance of a provider."""
        name_lower = provider_name.lower()
        if name_lower not in self._instances:
            provider_cls = provider_registry.get_provider_class(name_lower)
            self._instances[name_lower] = provider_cls()
        return self._instances[name_lower]

    async def initialize_all(self) -> None:
        """Initializes all instantiated providers."""
        for instance in self._instances.values():
            await instance.initialize()

    async def shutdown_all(self) -> None:
        """Shuts down all instantiated providers."""
        for instance in self._instances.values():
            await instance.shutdown()


provider_factory = ProviderFactory()
