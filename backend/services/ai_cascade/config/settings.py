import os
import yaml
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(__file__).parent


class CascadeSettings:
    def __init__(self):
        self.providers: Dict[str, Any] = {}
        self.pipelines: Dict[str, Any] = {}
        self.load_configs()

    def load_configs(self):
        providers_path = CONFIG_DIR / "providers.yaml"
        pipelines_path = CONFIG_DIR / "pipelines.yaml"

        if providers_path.exists():
            with open(providers_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "providers" in data:
                    self.providers = data["providers"]

        if pipelines_path.exists():
            with open(pipelines_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "pipelines" in data:
                    self.pipelines = data["pipelines"]

        # Startup Validation: Ensure configs loaded successfully
        if not self.providers:
            raise ValueError("Startup Config Validation Failed: No providers configured in providers.yaml")
        if not self.pipelines:
            raise ValueError("Startup Config Validation Failed: No pipelines configured in pipelines.yaml")

        # Validate providers config structure
        for provider_name, cfg in self.providers.items():
            required_keys = ["enabled", "priority", "timeout", "retries", "cooldown", "circuit_threshold"]
            for key in required_keys:
                if key not in cfg:
                    raise ValueError(f"Startup Config Validation Failed: Provider '{provider_name}' missing required config key '{key}'")

        # Validate pipelines config structure
        for pipeline_name, cfg in self.pipelines.items():
            required_keys = ["cache", "validator", "providers"]
            for key in required_keys:
                if key not in cfg:
                    raise ValueError(f"Startup Config Validation Failed: Pipeline '{pipeline_name}' missing required config key '{key}'")

        # Verify all scheduler jobs have misfire_grace_time=60
        scheduler_path = CONFIG_DIR / "../../../scheduler/scheduler.py"
        if scheduler_path.exists():
            with open(scheduler_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Split by add_job to isolate the arguments block of each registration
            blocks = content.split("add_job(")[1:]
            for idx, block in enumerate(blocks):
                # Isolate the job's arguments by looking up to the closing ')' of add_job
                # To handle nested parentheses, we check if misfire_grace_time is in the block before the next add_job
                if "misfire_grace_time=60" not in block:
                    raise ValueError(f"Startup Config Validation Failed: Scheduler job {idx + 1} missing misfire_grace_time=60: {block[:100]}")

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        return self.providers.get(provider_name, {})

    def get_pipeline_config(self, pipeline_name: str) -> Dict[str, Any]:
        return self.pipelines.get(pipeline_name, {})

    # Feature Flags from Environment variables
    @property
    def enable_cerebras(self) -> bool:
        return os.getenv("ENABLE_CEREBRAS", "true").lower() == "true"

    @property
    def enable_cache(self) -> bool:
        return os.getenv("ENABLE_CACHE", "true").lower() == "true"

    @property
    def enable_repair(self) -> bool:
        return os.getenv("ENABLE_REPAIR", "true").lower() == "true"

    @property
    def enable_analytics(self) -> bool:
        return os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"

    @property
    def enable_events(self) -> bool:
        return os.getenv("ENABLE_EVENTS", "true").lower() == "true"

    @property
    def enable_json_repair(self) -> bool:
        return os.getenv("ENABLE_JSON_REPAIR", "true").lower() == "true"

    @property
    def enable_capability_planner(self) -> bool:
        return os.getenv("ENABLE_CAPABILITY_PLANNER", "false").lower() == "true"

    @property
    def benchmark_mock(self) -> bool:
        return os.getenv("BENCHMARK_MOCK", "true").lower() == "true"


settings = CascadeSettings()
