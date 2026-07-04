import base64
import re
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
    COMPUTE_PROVIDER: str | None = None
    INTERNAL_API_KEY: str | None = "dev_internal_api_key"
    
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    
    VITE_API_URL: str | None = None
    VITE_BOT_USERNAME: str | None = None
    HF_TOKEN: str | None = None
    COBALT_API_URL: str | None = None
    BROWSER_FOR_COOKIES: str | None = None
    IG_COOKIES_B64: str | None = None

    ENV: str = "development"



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

        # 2. Validate JWT_SECRET (must be at least 32 hex characters)
        if len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")
        if not re.match(r"^[0-9a-fA-F]+$", self.JWT_SECRET):
            raise ValueError("JWT_SECRET must be a hex-encoded string.")

        # 3. Validate TELEGRAM_BOT_TOKEN format (\d+:[A-Za-z0-9_-]{35})
        if not re.match(r"^\d+:[A-Za-z0-9_-]{35}$", self.TELEGRAM_BOT_TOKEN):
            raise ValueError("TELEGRAM_BOT_TOKEN must match format '\\d+:[A-Za-z0-9_-]{35}'")


# Central settings singleton
try:
    settings = Settings()
    if settings and settings.HF_TOKEN:
        import os
        os.environ["HF_TOKEN"] = settings.HF_TOKEN
except Exception as e:
    # Fail fast on startup if settings are missing or misconfigured
    print(f"CRITICAL CONFIGURATION ERROR on startup: {e}")
    # We do not raise settings here to allow import in unit tests where we mock the env.
    settings = None
