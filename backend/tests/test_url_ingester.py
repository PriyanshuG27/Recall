import pytest
import unittest.mock as mock
from backend.services.url_ingester import ingest_url, scrape_url

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
        return (201,)

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
    mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "Mock summary", "tags": ["url", "test"]})
    monkeypatch.setattr("backend.services.url_ingester.AICascade", lambda: mock_cascade)
    monkeypatch.setattr("backend.services.url_ingester.embed_text", mock.AsyncMock(return_value=[0.1]*384))
    monkeypatch.setattr("backend.services.url_ingester.encrypt", lambda x: "encrypted_" + x)
    return mock_cascade

@pytest.mark.asyncio
async def test_scrape_url_success(monkeypatch):
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><head><title>Test Title</title></head><body><p>Hello World</p></body></html>"
    
    async def mock_get(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    title, text = await scrape_url("https://example.com")
    assert title == "Test Title"
    assert "Hello World" in text

@pytest.mark.asyncio
async def test_scrape_url_failure(monkeypatch):
    mock_resp = mock.Mock()
    mock_resp.status_code = 404
    
    async def mock_get(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    title, text = await scrape_url("https://example.com")
    assert title == "https://example.com"
    assert text == "https://example.com"

@pytest.mark.asyncio
async def test_ingest_url_success(monkeypatch, mock_deps):
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><head><title>Success Title</title></head><body><p>Clean text</p></body></html>"
    
    async def mock_get(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    
    conn = MockConnection()
    item_id = await ingest_url("https://example.com", user_id=4, db=conn)
    assert item_id == 201
    
    # Verify execute calls
    executed = conn.cursor_inst.executed
    assert len(executed) == 1
    query, params = executed[0]
    assert "INSERT INTO items" in query
    assert params[0] == 4
    assert params[1] == "https://example.com"
    assert params[3] == "Mock summary"
    assert params[4] == "Success Title"
    assert params[6] == ["url", "test"]
