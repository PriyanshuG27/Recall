import pytest
from pydantic import ValidationError
from backend.config import Settings

# Helper for valid mock settings dict
def get_valid_mock_env():
    return {
        "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
        "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
        "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
        "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
        "WEBSITE_URL": "http://localhost:5173"
    }

def test_valid_config(monkeypatch):
    env = get_valid_mock_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    assert settings.TELEGRAM_BOT_TOKEN == env["TELEGRAM_BOT_TOKEN"]
    assert settings.DATABASE_URL == env["DATABASE_URL"]
    
    # Verify validation succeeds
    settings.validate_crypto_keys()

def test_missing_required_var(monkeypatch):
    env = get_valid_mock_env()
    # Remove a required key
    env.pop("TELEGRAM_BOT_TOKEN")
    
    # Clear env to ensure it's not present
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    with pytest.raises(ValidationError):
        Settings()

def test_invalid_fernet_key_length(monkeypatch):
    env = get_valid_mock_env()
    # Invalid length (decoded is not 32 bytes)
    env["FERNET_KEY"] = "not-base64-and-short"
    
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(ValueError, match="FERNET_KEY"):
        settings.validate_crypto_keys()

def test_invalid_fernet_key_base64(monkeypatch):
    env = get_valid_mock_env()
    # Invalid base64 characters
    env["FERNET_KEY"] = "!!!" * 15
    
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(ValueError, match="FERNET_KEY"):
        settings.validate_crypto_keys()

def test_invalid_jwt_secret_length(monkeypatch):
    env = get_valid_mock_env()
    # Too short (must be at least 32 chars)
    env["JWT_SECRET"] = "abc123hex"
    
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_crypto_keys()

def test_invalid_jwt_secret_chars(monkeypatch):
    env = get_valid_mock_env()
    # Contains non-hex chars (like 'g')
    env["JWT_SECRET"] = "g" * 32
    
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_crypto_keys()

def test_invalid_telegram_token(monkeypatch):
    env = get_valid_mock_env()
    # Invalid pattern (does not match \d+:[A-Za-z0-9_-]{35})
    env["TELEGRAM_BOT_TOKEN"] = "invalid_bot_token"
    
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        settings.validate_crypto_keys()

def test_settings_redaction(monkeypatch):
    env = get_valid_mock_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    assert repr(settings) == "<Settings: [REDACTED]>"
    assert str(settings) == "<Settings: [REDACTED]>"

def test_settings_serialization_blocked(monkeypatch):
    env = get_valid_mock_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
        
    settings = Settings()
    with pytest.raises(TypeError, match="serialization is disabled"):
        settings.model_dump()
        
    with pytest.raises(TypeError, match="serialization is disabled"):
        settings.model_dump_json()
