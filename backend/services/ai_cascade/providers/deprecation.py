import logging
import asyncio
from backend.services.ai_cascade.config import settings
from backend.services.ai_cascade.shared.exceptions import ModelDeprecationError
from backend.services.ai_cascade.events.event_bus import event_bus, ModelDeprecatedWarning

logger = logging.getLogger(__name__)

class DeprecationManager:
    @staticmethod
    def check_model_deprecation(provider: str, model: str) -> None:
        """
        Validates model lifecycle status before executing LLM task.
        Raises ModelDeprecationError if model is retired.
        Logs warning and publishes event if model is deprecated.
        """
        provider_cfg = settings.get_provider_config(provider)
        models_cfg = provider_cfg.get("models", {})
        model_info = models_cfg.get(model)

        if not model_info:
            return

        status = model_info.get("status", "active").lower()
        replacement = model_info.get("replacement", "none")

        if status == "retired":
            logger.error("DeprecationManager: Attempted to run retired model '%s' on provider '%s'.", model, provider)
            raise ModelDeprecationError(
                f"Model '{model}' on provider '{provider}' is retired and cannot be run. "
                f"Suggested replacement: '{replacement}'"
            )

        if status == "deprecated":
            logger.warning(
                "DeprecationManager: Model '%s' on provider '%s' is deprecated. "
                "Please plan to migrate to replacement model '%s'.",
                model, provider, replacement
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_bus.publish(ModelDeprecatedWarning(
                    provider=provider,
                    model=model,
                    replacement=replacement
                )))
            except RuntimeError:
                pass


deprecation_manager = DeprecationManager()
