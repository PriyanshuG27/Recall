import base64
import re
import logging
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ==========================================================================
    # REQUIRED VARIABLES (ValidationError raised if missing at startup)
    # ==========================================================================
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str
    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str
    FERNET_KEY: str
    JWT_SECRET: str
    WEBSITE_URL: str

    # ==========================================================================
    # OPTIONAL VARIABLES (Defaults to None)
    # ==========================================================================
    MODAL_API_TOKEN: str | None = None
    MODAL_SUMMARY_URL: str | None = None
    MODAL_TRANSCRIBE_URL: str | None = None
    MODAL_RAG_URL: str | None = None
    MODAL_TAGS_URL: str | None = None
    MODAL_EMBED_URL: str | None = None
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    NVIDIA_API_KEY: str | None = None
    CEREBRAS_API_KEY: str | None = None
    COMPUTE_PROVIDER: str | None = None
    INTERNAL_API_KEY: str | None = "dev_internal_api_key"
    TELEGRAM_WEBHOOK_SECRET: str | None = None
    
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    
    VITE_API_URL: str | None = None
    VITE_BOT_USERNAME: str | None = None
    HF_TOKEN: str | None = None
    COBALT_API_URL: str | None = None
    COBALT_API_KEY: str | None = None
    BROWSER_FOR_COOKIES: str | None = None
    IG_COOKIES_B64: str | None = None

    ENV: str = "development"
    USE_NEW_CASCADE: bool = True

    # Reranker settings
    ENABLE_RERANKING: bool = True
    RERANK_PRELOAD_ON_STARTUP: bool = True
    RERANKER_PROVIDER: str = "fastembed"
    RERANKER_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    RERANK_CANDIDATES: int = 20
    RERANK_TOP_N: int = 5
    RERANK_TIMEOUT_SECONDS: float = 2.0

    # Contextual Retrieval settings
    CHUNK_TARGET_WORDS: int = 120
    CHUNK_MIN_WORDS: int = 80
    CHUNK_MAX_WORDS: int = 180
    CHUNK_OVERLAP_SENTENCES: int = 1
    PARENT_TARGET_WORDS: int = 400
    MAX_EXPANDED_WORDS: int = 500

    # Entity Resolution settings
    ENTITY_RESOLUTION_THRESHOLD: float = 0.85

    # Semantic Chunking settings
    SEMANTIC_SPLIT_THRESHOLD: float = 0.65
    DEFAULT_CHUNK_VERSION: int = 2

    # Search & Fusion parameters (Phase 2.8)
    RRF_K: int = 60
    RRF_VECTOR_WEIGHT: float = 1.0
    RRF_TEXT_WEIGHT: float = 1.0
    ENABLE_QUERY_REWRITING: bool = True
    QUERY_REWRITE_TIMEOUT_SECONDS: float = 1.5
    QUERY_REWRITE_MAX_WORDS: int = 2
    TRIGRAM_MIN_SIMILARITY: float = 0.3

    @field_validator("RRF_VECTOR_WEIGHT", "RRF_TEXT_WEIGHT")
    @classmethod
    def validate_rrf_weights(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("RRF weights must be strictly positive (> 0).")
        return v

    # Hub selection parameters
    HUB_FREQUENCY_WEIGHT: float = 1.0
    HUB_RECENCY_WEIGHT: float = 1.5
    HUB_VELOCITY_WEIGHT: float = 2.0
    HUB_HYSTERESIS_BOOST: float = 1.15
    HUB_DIVERSITY_THRESHOLD: float = 0.70
    HUB_MIN_LIFESPAN_DAYS: int = 7



    # ==========================================================================
    # CONFIGURATION & OVERRIDES
    # ==========================================================================
    model_config = SettingsConfigDict(
        # Load multiple potential env file locations (later paths override earlier ones)
        env_file=(
            ".env", 
            "backend/.env", 
            ".env.local", 
            "backend/.env.local"
        ),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ==========================================================================
    # SECURITY GUARDS
    # ==========================================================================
    def __repr__(self) -> str:
        """Prevent accidental logging of sensitive configurations."""
        return "<Settings: [REDACTED]>"

    def __str__(self) -> str:
        """Prevent printing of sensitive configurations."""
        return "<Settings: [REDACTED]>"

    def model_dump(self, *args, **kwargs):
        """Block serialization to dict for security."""
        raise TypeError("Settings object serialization is disabled for security reasons.")

    def model_dump_json(self, *args, **kwargs):
        """Block serialization to JSON for security."""
        raise TypeError("Settings object serialization is disabled for security reasons.")

    # ==========================================================================
    # VALIDATION
    # ==========================================================================
    def validate_crypto_keys(self) -> None:
        """
        Validates the structure and strength of essential cryptographic keys:
        - FERNET_KEY must be a valid 32-byte key after base64 decoding.
        - JWT_SECRET must be at least 32 hex characters.
        - TELEGRAM_BOT_TOKEN must match the standard Telegram token format.
        """
        # 1. Validate FERNET_KEY format (must be 32 bytes after base64 decode)
        try:
            decoded = base64.urlsafe_b64decode(self.FERNET_KEY.encode())
            if len(decoded) != 32:
                raise ValueError(f"Decoded Fernet key is {len(decoded)} bytes (must be exactly 32 bytes)")
        except Exception as e:
            raise ValueError(f"FERNET_KEY must be valid URL-safe base64 (32 bytes decoded): {e}")

        # 2. Validate JWT_SECRET (must be at least 32 characters long.)
        if len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")
        if not re.match(r"^[0-9a-fA-F]+$", self.JWT_SECRET):
            raise ValueError("JWT_SECRET must be a hex-encoded string.")

        # 3. Validate TELEGRAM_BOT_TOKEN format (\d+:[A-Za-z0-9_-]{35})
        if not re.match(r"^\d+:[A-Za-z0-9_-]{35}$", self.TELEGRAM_BOT_TOKEN):
            raise ValueError("TELEGRAM_BOT_TOKEN must match format '\\d+:[A-Za-z0-9_-]{35}'")


# Central settings singleton
class SecretMaskingFilter(logging.Filter):
    def __init__(self, secrets: list[str] = None):
        super().__init__()
        self.secrets = sorted([s for s in (secrets or []) if s], key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.secrets:
            return True
            
        def mask_string(val: str) -> str:
            if not isinstance(val, str):
                return val
            masked = val
            for secret in self.secrets:
                if len(secret) > 4:
                    masked = masked.replace(secret, "[REDACTED]")
            return masked

        if isinstance(record.msg, str):
            record.msg = mask_string(record.msg)
            
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: (mask_string(v) if isinstance(v, str) else v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(mask_string(v) if isinstance(v, str) else v for v in record.args)
                
        return True

def setup_logging(settings_obj: Settings) -> None:
    secrets = []
    if settings_obj:
        for field in [
            "TELEGRAM_BOT_TOKEN", "FERNET_KEY", "JWT_SECRET", 
            "UPSTASH_REDIS_REST_TOKEN", "MODAL_API_TOKEN", 
            "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", 
            "NVIDIA_API_KEY", "CEREBRAS_API_KEY", "GOOGLE_CLIENT_SECRET"
        ]:
            val = getattr(settings_obj, field, None)
            if val and isinstance(val, str):
                secrets.append(val)
                
    mask_filter = SecretMaskingFilter(secrets)
    
    # Configure basic logger root
    logging.basicConfig(level=logging.INFO)
    root = logging.getLogger()
    root.addFilter(mask_filter)
    for h in root.handlers:
        h.addFilter(mask_filter)
        
    # Apply to existing loggers
    for logger_name in logging.root.manager.loggerDict:
        log = logging.getLogger(logger_name)
        log.addFilter(mask_filter)
        for h in log.handlers:
            h.addFilter(mask_filter)

try:
    settings = Settings()
    if settings:
        setup_logging(settings)
        if settings.HF_TOKEN:
            import os
            os.environ["HF_TOKEN"] = settings.HF_TOKEN
except Exception as e:
    # Fail fast on startup if settings are missing or misconfigured
    print(f"CRITICAL CONFIGURATION ERROR on startup: {e}")
    # We do not raise settings here to allow import in unit tests where we mock the env.
    settings = None
