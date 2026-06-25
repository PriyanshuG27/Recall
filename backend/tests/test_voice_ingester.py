import pytest
import unittest.mock as mock
import os
from backend.services.voice_ingester import ingest_voice, download_telegram_file
from backend.config import settings

class MockCursor:
    def __init__(self):
        self.executed = []
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        if self.executed and "SELECT id FROM items" in self.executed[-1][0]:
            # For the duplicate check: if query has SELECT id, return None to simulate no duplicate by default
            return None
        return (301,)

class MockConnection:
    def __init__(self):
        self.cursor_inst = MockCursor()
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

@pytest.fixture
def mock_deps(monkeypatch):
    mock_cascade = mock.MagicMock()
    mock_cascade.transcribe = mock.AsyncMock(return_value="Hello, this is a voice note transcript.")
    mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "Voice note summary", "tags": ["voice", "memo"]})
    monkeypatch.setattr("backend.services.voice_ingester.AICascade", lambda: mock_cascade)
    monkeypatch.setattr("backend.services.voice_ingester.embed_text", mock.AsyncMock(return_value=[0.2]*384))
    monkeypatch.setattr("backend.services.voice_ingester.encrypt", lambda x: "encrypted_" + x)
    return mock_cascade

@pytest.mark.asyncio
async def test_download_telegram_file_success(monkeypatch):
    # Save token
    orig_token = settings.TELEGRAM_BOT_TOKEN
    settings.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF"
    
    mock_get_file_resp = mock.Mock()
    mock_get_file_resp.status_code = 200
    mock_get_file_resp.json = mock.Mock(return_value={
        "ok": True,
        "result": {
            "file_path": "voice/file_0.ogg",
            "file_size": 1000
        }
    })
    
    mock_download_resp = mock.Mock()
    mock_download_resp.status_code = 200
    mock_download_resp.content = b"fake ogg bytes"
    
    async def mock_get(self_client, url, *args, **kwargs):
        if "getFile" in url:
            return mock_get_file_resp
        return mock_download_resp
        
    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)

    class MockStreamContext:
        def __init__(self, response):
            self.response = response
        async def __aenter__(self):
            return self.response
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_stream_resp = mock.Mock()
    mock_stream_resp.status_code = 200
    mock_stream_resp.raise_for_status = mock.Mock()
    
    async def mock_aiter_bytes(*args, **kwargs):
        yield b"fake ogg bytes"
        
    mock_stream_resp.aiter_bytes = mock_aiter_bytes

    def mock_stream(self_client, method, url, *args, **kwargs):
        return MockStreamContext(mock_stream_resp)
        
    monkeypatch.setattr("httpx.AsyncClient.stream", mock_stream)
    
    # Mock open
    mock_open = mock.mock_open()
    monkeypatch.setattr("builtins.open", mock_open)
    
    try:
        path = await download_telegram_file("file_id_123", "dummy_dir", "dummy_uuid")
        expected_path = os.path.join("dummy_dir", "dummy_uuid.ogg")
        assert path == expected_path
        mock_open.assert_called_once_with(expected_path, "wb")
        mock_open().write.assert_called_once_with(b"fake ogg bytes")
    finally:
        settings.TELEGRAM_BOT_TOKEN = orig_token

@pytest.mark.asyncio
async def test_ingest_voice_success(monkeypatch, mock_deps):
    # Mock download_telegram_file
    monkeypatch.setattr(
        "backend.services.voice_ingester.download_telegram_file",
        mock.AsyncMock(return_value="dummy_path.ogg")
    )
    
    # Mock open for reading voice note
    mock_open = mock.mock_open(read_data=b"fake ogg bytes")
    monkeypatch.setattr("builtins.open", mock_open)
    
    # Mock os.path.exists and os.remove
    monkeypatch.setattr("os.path.exists", lambda path: True)
    mock_remove = mock.Mock()
    monkeypatch.setattr("os.remove", mock_remove)
    
    conn = MockConnection()
    item_id = await ingest_voice("file_id_123", user_id=4, chat_id="12345", db=conn)
    assert item_id == 301
    
    # Check executed query
    executed = conn.cursor_inst.executed
    assert len(executed) == 2
    
    # First query should be the duplicate check
    select_query, select_params = executed[0]
    assert "SELECT id FROM items" in select_query
    assert select_params[0] == 4
    
    # Second query should be the INSERT
    insert_query, insert_params = executed[1]
    assert "INSERT INTO items" in insert_query
    assert insert_params[0] == 4
    assert insert_params[1] == "file_id_123"
    assert insert_params[2] == "encrypted_Hello, this is a voice note transcript."
    assert insert_params[3] == "Voice note summary"
    assert insert_params[4] == "Hello, this is a voice note transcript."
    assert insert_params[6] == ["voice", "memo"]
    
    mock_remove.assert_called_once()

@pytest.mark.asyncio
async def test_ingest_voice_duplicate(monkeypatch, mock_deps):
    # Mock download_telegram_file
    monkeypatch.setattr(
        "backend.services.voice_ingester.download_telegram_file",
        mock.AsyncMock(return_value="dummy_path.ogg")
    )
    
    # Mock open for reading voice note
    mock_open = mock.mock_open(read_data=b"fake ogg bytes")
    monkeypatch.setattr("builtins.open", mock_open)
    
    # Mock os.path.exists and os.remove
    monkeypatch.setattr("os.path.exists", lambda path: True)
    mock_remove = mock.Mock()
    monkeypatch.setattr("os.remove", mock_remove)
    
    # Override MockCursor to return a duplicate row id
    class DuplicateCursor(MockCursor):
        async def fetchone(self):
            return (404,)
            
    class DuplicateConnection(MockConnection):
        def __init__(self):
            self.cursor_inst = DuplicateCursor()
            
    conn = DuplicateConnection()
    from backend.exceptions import DuplicateItemException
    with pytest.raises(DuplicateItemException) as excinfo:
        await ingest_voice("file_id_123", user_id=4, chat_id="12345", db=conn)
        
    assert excinfo.value.item_id == 404
    mock_remove.assert_called_once()
