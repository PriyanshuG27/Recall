from typing import List
from backend.services.ai_cascade.registry.model_registry import ModelRegistry, ModelMetadata, ModelCapability


class CapabilityPlanner:
    def plan_capabilities(
        self,
        required_capabilities: List[ModelCapability],
        max_context_needed: int = 0
    ) -> List[ModelMetadata]:
        """
        Queries the ModelRegistry to find and rank all active models
        supporting the required capabilities and satisfying the context window requirement.
        """
        candidates = []
        # Access internal models map from registry
        for model in ModelRegistry._models.values():
            if not model.is_active:
                continue

            # Verify all required capabilities exist on this model
            has_all = all(cap in model.capabilities for cap in required_capabilities)
            if not has_all:
                continue

            # Verify context window constraints
            if max_context_needed > 0 and model.context_window < max_context_needed:
                continue

            candidates.append(model)

        # Basic default sorting: higher context windows first, then low-latency class first
        candidates.sort(key=lambda m: (m.context_window, -1 if m.latency_class == "low" else 0), reverse=True)
        return candidates
