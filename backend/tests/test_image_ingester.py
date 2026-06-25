import pytest
import unittest.mock as mock
from backend.services.image_ingester import ingest_image, download_telegram_image
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
            # For the duplicate check: return None to simulate no duplicate by default
            return None
        return (401,)

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
    mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "OCR Summary", "tags": ["image", "ocr"]})
    mock_cascade.caption_image = mock.AsyncMock(return_value="Gemini photo caption description.")
    monkeypatch.setattr("backend.services.image_ingester.AICascade", lambda: mock_cascade)
    monkeypatch.setattr("backend.services.image_ingester.embed_text", mock.AsyncMock(return_value=[0.3]*384))
    monkeypatch.setattr("backend.services.image_ingester.encrypt", lambda x: "encrypted_" + x)
    return mock_cascade

@pytest.mark.asyncio
async def test_download_telegram_image_success(monkeypatch):
    orig_token = settings.TELEGRAM_BOT_TOKEN
    settings.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF"
    
    mock_get_file_resp = mock.Mock()
    mock_get_file_resp.status_code = 200
    mock_get_file_resp.json = mock.Mock(return_value={
        "ok": True,
        "result": {
            "file_path": "photos/file_0.jpg",
            "file_size": 1000
        }
    })
    
    mock_download_resp = mock.Mock()
    mock_download_resp.status_code = 200
    mock_download_resp.content = b"fake jpg bytes"
    
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
        yield b"fake jpg bytes"
        
    mock_stream_resp.aiter_bytes = mock_aiter_bytes

    def mock_stream(self_client, method, url, *args, **kwargs):
        return MockStreamContext(mock_stream_resp)
        
    monkeypatch.setattr("httpx.AsyncClient.stream", mock_stream)
    
    # Mock open
    mock_open = mock.mock_open()
    monkeypatch.setattr("builtins.open", mock_open)
    
    try:
        await download_telegram_image("file_id_456", "dummy_image.jpg")
        mock_open.assert_called_once_with("dummy_image.jpg", "wb")
        mock_open().write.assert_called_once_with(b"fake jpg bytes")
    finally:
        settings.TELEGRAM_BOT_TOKEN = orig_token

@pytest.mark.asyncio
async def test_ingest_image_ocr_path(monkeypatch, mock_deps):
    monkeypatch.setattr("backend.services.image_ingester.download_telegram_image", mock.AsyncMock(return_value=None))
    
    mock_open = mock.mock_open(read_data=b"fake jpg bytes")
    monkeypatch.setattr("builtins.open", mock_open)
    
    monkeypatch.setattr("os.path.exists", lambda path: True)
    mock_remove = mock.Mock()
    monkeypatch.setattr("os.remove", mock_remove)
    
    # Mock PIL and Tesseract to return high length text
    monkeypatch.setattr("PIL.Image.open", lambda path: mock.Mock())
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "This is a very long OCR text block that is definitely longer than fifty characters to force OCR path.")
    
    conn = MockConnection()
    item_id = await ingest_image("file_id_456", user_id=4, chat_id="12345", db=conn)
    assert item_id == 401
    
    executed = conn.cursor_inst.executed
    assert len(executed) == 2
    query, params = executed[1]
    assert "INSERT INTO items" in query
    assert params[0] == 4
    assert params[1] == "file_id_456"
    assert "OCR Text:" in params[2]
    assert params[3] == "OCR Summary"
    assert params[4].startswith("OCR: This is a very long OCR text")
    assert params[6] == ["image", "ocr"]

@pytest.mark.asyncio
async def test_ingest_image_caption_fallback_path(monkeypatch, mock_deps):
    monkeypatch.setattr("backend.services.image_ingester.download_telegram_image", mock.AsyncMock(return_value=None))
    
    mock_open = mock.mock_open(read_data=b"fake ogg bytes")
    monkeypatch.setattr("builtins.open", mock_open)
    
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("os.remove", mock.Mock())
    
    # Mock Tesseract to raise error (simulating not installed)
    def mock_ocr_fail(*args, **kwargs):
        raise RuntimeError("tesseract not found")
    monkeypatch.setattr("PIL.Image.open", lambda path: mock.Mock())
    monkeypatch.setattr("pytesseract.image_to_string", mock_ocr_fail)
    
    conn = MockConnection()
    item_id = await ingest_image("file_id_456", user_id=4, chat_id="12345", db=conn)
    assert item_id == 401
    
    # Check executed query uses Gemini caption description
    executed = conn.cursor_inst.executed
    assert len(executed) == 2
    query, params = executed[1]
    assert "INSERT INTO items" in query
    assert params[0] == 4
    assert params[1] == "file_id_456"
    assert "Image Caption:\nGemini photo caption description." in params[2]
    assert params[3] == "Gemini photo caption description."
    assert params[4] == "Image: Gemini photo caption description."
    assert params[6] == ["image", "caption"]

@pytest.mark.asyncio
async def test_ingest_image_duplicate(monkeypatch, mock_deps):
    monkeypatch.setattr("backend.services.image_ingester.download_telegram_image", mock.AsyncMock(return_value=None))
    
    mock_open = mock.mock_open(read_data=b"fake jpg bytes")
    monkeypatch.setattr("builtins.open", mock_open)
    
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("os.remove", mock.Mock())
    
    monkeypatch.setattr("PIL.Image.open", lambda path: mock.Mock())
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "OCR output text")
    
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
        await ingest_image("file_id_456", user_id=4, chat_id="12345", db=conn)
        
    assert excinfo.value.item_id == 404
