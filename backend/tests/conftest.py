"""
backend/tests/conftest.py
==========================
Shared pytest fixtures and configuration for the Recall test suite.

Ensures:
  - sys.path is set so `from backend.x import y` works from any CWD.
  - A valid mock environment is injected for all tests that need settings.
  - All external calls (DB, Redis, AI APIs) are mocked — zero network calls in CI.
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — add project root to sys.path so `backend.*` imports resolve
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # D:\Recall
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Shared mock environment
# ---------------------------------------------------------------------------
VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    # Valid Fernet key (32 bytes decoded from URL-safe base64)
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
    "ENV": "test",
}


@pytest.fixture()
def mock_env(monkeypatch):
    """
    Inject a complete valid environment for tests that need settings to load.
    Usage:
        def test_something(mock_env):
            from backend.config import Settings
            s = Settings()
            ...
    """
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return VALID_ENV
