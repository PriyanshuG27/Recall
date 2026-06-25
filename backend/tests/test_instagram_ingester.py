import os
import io
import json
import pytest
import unittest.mock as mock
import uuid

from backend.services.youtube_ingester import ingest_instagram, _convert_cookies_json_to_netscape


# ─── Shared DB mocks ────────────────────────────────────────────────────────

class MockCursor:
    def __init__(self):
        self.executed = []
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def execute(self, q, p=None): self.executed.append((q, p))
    async def fetchone(self): return (202,)

class MockConnection:
    def __init__(self): self.cursor_inst = MockCursor()
    def cursor(self): return self.cursor_inst
    async def commit(self): pass


# ─── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_ai(monkeypatch):
    cascade = mock.MagicMock()
    cascade.transcribe = mock.AsyncMock(return_value="Mocked Instagram transcript")
    cascade.summarise = mock.AsyncMock(return_value={"summary": "Mocked summary", "tags": ["instagram"]})
    monkeypatch.setattr("backend.services.youtube_ingester.AICascade", lambda: cascade)
    monkeypatch.setattr("backend.services.youtube_ingester.embed_text", mock.AsyncMock(return_value=[0.1] * 384))
    monkeypatch.setattr("backend.services.youtube_ingester.encrypt", lambda x: "enc:" + x)
    monkeypatch.setattr("uuid.uuid4", lambda: uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    return cascade

@pytest.fixture
def mock_settings_cobalt(monkeypatch):
    class S:
        COBALT_API_URL = "https://cobalt.example.com"
    monkeypatch.setattr("backend.config.settings", S)

@pytest.fixture
def mock_settings_no_cobalt(monkeypatch):
    class S:
        COBALT_API_URL = None
    monkeypatch.setattr("backend.config.settings", S)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def mock_open_dispatch(file, mode="r", *a, **kw):
    """Route open() calls by mode so audio reads return bytes."""
    if "b" in mode:
        return io.BytesIO(b"audio_bytes")
    return io.StringIO("")


# ─── Tests: Cobalt happy path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cobalt_happy_path(monkeypatch, mock_ai, mock_settings_cobalt):
    """Cobalt resolves URL, audio downloads, transcription succeeds → full item saved."""
    monkeypatch.setattr(
        "backend.services.youtube_ingester._try_cobalt",
        mock.AsyncMock(return_value="https://cdn.example.com/audio.mp3"),
    )
    monkeypatch.setattr(
        "backend.services.youtube_ingester._download_audio_from_url",
        mock.AsyncMock(return_value=True),
    )
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr("os.path.getsize", lambda p: 1024)
    monkeypatch.setattr("os.remove", lambda p: None)

    class MockYDL:
        def __init__(self, opts=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=False): return {"title": "Cool Reel", "duration": 30}
        def download(self, urls): pass

    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYDL)

    conn = MockConnection()
    with mock.patch("backend.services.youtube_ingester.open", side_effect=mock_open_dispatch):
        item_id = await ingest_instagram("https://www.instagram.com/reel/abc/", 7, conn)

    assert item_id == 202
    q, params = conn.cursor_inst.executed[0]
    assert "INSERT INTO items" in q
    assert params[0] == 7
    assert "Mocked summary" in params[3]
    assert params[4] == "Cool Reel"


# ─── Tests: Cobalt fails → yt-dlp fallback ───────────────────────────────────

@pytest.mark.asyncio
async def test_cobalt_fails_ytdlp_succeeds(monkeypatch, mock_ai, mock_settings_cobalt):
    """Cobalt returns None → yt-dlp direct download succeeds."""
    monkeypatch.setattr(
        "backend.services.youtube_ingester._try_cobalt",
        mock.AsyncMock(return_value=None),
    )
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr("os.path.getsize", lambda p: 1024)
    monkeypatch.setattr("os.remove", lambda p: None)

    class MockYDL:
        def __init__(self, opts=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=False): return {"title": "Fallback Reel", "duration": 30}
        def download(self, urls): pass

    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYDL)
    monkeypatch.setattr("os.listdir", lambda p: ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.mp3"])

    conn = MockConnection()
    with mock.patch("backend.services.youtube_ingester.open", side_effect=mock_open_dispatch):
        item_id = await ingest_instagram("https://www.instagram.com/reel/abc/", 7, conn)

    assert item_id == 202
    q, params = conn.cursor_inst.executed[0]
    assert "Mocked summary" in params[3]


# ─── Tests: both tiers fail → bookmark ───────────────────────────────────────

@pytest.mark.asyncio
async def test_all_tiers_fail_bookmark(monkeypatch, mock_ai, mock_settings_cobalt):
    """Cobalt + yt-dlp both fail → bookmark saved."""
    monkeypatch.setattr(
        "backend.services.youtube_ingester._try_cobalt",
        mock.AsyncMock(return_value=None),
    )
    monkeypatch.setattr("os.path.exists", lambda p: False)
    monkeypatch.setattr("os.remove", lambda p: None)

    class MockYDL:
        def __init__(self, opts=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=False): raise RuntimeError("blocked")
        def download(self, urls): raise RuntimeError("blocked")

    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYDL)

    conn = MockConnection()
    item_id = await ingest_instagram("https://www.instagram.com/reel/abc/", 7, conn)

    assert item_id == 202
    q, params = conn.cursor_inst.executed[0]
    assert "Could not process this Instagram Reel" in params[3]
    assert "Bookmark: Instagram Video" == params[4]


# ─── Tests: no Cobalt URL configured ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_cobalt_url_goes_straight_to_ytdlp(monkeypatch, mock_ai, mock_settings_no_cobalt):
    """When COBALT_API_URL is None, skips Cobalt and tries yt-dlp directly."""
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr("os.path.getsize", lambda p: 512)
    monkeypatch.setattr("os.remove", lambda p: None)

    class MockYDL:
        def __init__(self, opts=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=False): return {"title": "No Cobalt Reel", "duration": 20}
        def download(self, urls): pass

    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYDL)
    monkeypatch.setattr("os.listdir", lambda p: ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.mp3"])

    conn = MockConnection()
    with mock.patch("backend.services.youtube_ingester.open", side_effect=mock_open_dispatch):
        item_id = await ingest_instagram("https://www.instagram.com/reel/abc/", 7, conn)

    assert item_id == 202
    _, params = conn.cursor_inst.executed[0]
    assert "Mocked summary" in params[3]


# ─── Tests: cookie converter ─────────────────────────────────────────────────

def test_cookie_conversion_helper(tmp_path):
    """Converter writes correct Netscape tab-separated output."""
    cookies = [{"domain": ".instagram.com", "expirationDate": 1800000000,
                "name": "sessionid", "path": "/", "secure": True, "value": "abc123"}]
    jf = tmp_path / "cookies.json"
    tf = tmp_path / "cookies.txt"
    jf.write_text(json.dumps(cookies))

    assert _convert_cookies_json_to_netscape(str(jf), str(tf)) is True
    content = tf.read_text()
    assert "# Netscape HTTP Cookie File" in content
    assert ".instagram.com\tTRUE\t/\tTRUE\t1800000000\tsessionid\tabc123" in content

def test_cookie_conversion_missing_file():
    assert _convert_cookies_json_to_netscape("no_such_file.json", "out.txt") is False
