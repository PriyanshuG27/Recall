import pytest
import unittest.mock as mock
import uuid
from psycopg import AsyncConnection

from backend.services.youtube_ingester import ingest_youtube

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
        return (101,) # return mock item_id

class MockConnection:
    def __init__(self):
        self.cursor_inst = MockCursor()
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

# Mocking the AI services and embeddings
@pytest.fixture
def mock_dependencies(monkeypatch):
    # Mock AICascade
    mock_cascade = mock.MagicMock()
    mock_cascade.transcribe = mock.AsyncMock(return_value="Mocked Whisper Audio Transcript")
    mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "Mocked Video Summary", "tags": ["youtube", "test"]})
    monkeypatch.setattr("backend.services.youtube_ingester.AICascade", lambda: mock_cascade)
    
    # Mock embed_text
    monkeypatch.setattr("backend.services.youtube_ingester.embed_text", mock.AsyncMock(return_value=[0.1]*384))
    
    # Mock encrypt
    monkeypatch.setattr("backend.services.youtube_ingester.encrypt", lambda x: "encrypted_" + x)
    
    # Mock uuid to get consistent temp filename
    monkeypatch.setattr("uuid.uuid4", lambda: uuid.UUID("12345678-1234-5678-1234-567812345678"))
    
    # Mock youtube-transcript-api for all tests to avoid network calls
    class MockTranscriptSegment:
        def __init__(self, text):
            self.text = text
            self.start = 0.0
            self.duration = 1.0
            
    class MockTranscript:
        def __init__(self):
            self.language_code = "en"
        def fetch(self):
            return [MockTranscriptSegment("Mocked Subtitle segment 1"), MockTranscriptSegment("segment 2")]
            
    class MockTranscriptList:
        def find_transcript(self, langs):
            return MockTranscript()
        def __iter__(self):
            return iter([MockTranscript()])
            
    class MockYouTubeTranscriptApi:
        def list(self, video_id):
            return MockTranscriptList()
            
    monkeypatch.setattr("youtube_transcript_api.YouTubeTranscriptApi", MockYouTubeTranscriptApi)
    
    return mock_cascade

@pytest.mark.asyncio
async def test_youtube_audio_download_happy_path(monkeypatch, mock_dependencies):
    """Test that when audio download succeeds, it transcribes and ingests successfully."""
    mock_info = {
        "title": "Test YouTube Video",
        "duration": 300,
    }
    
    class MockYoutubeDL:
        def __init__(self, opts=None):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def extract_info(self, url, download=False):
            return mock_info
        def download(self, urls):
            pass
            
    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYoutubeDL)
    
    # Mock os.path.exists and listdir
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("os.listdir", lambda path: ["12345678-1234-5678-1234-567812345678.m4a"])
    monkeypatch.setattr("os.path.getsize", lambda path: 1024)
    monkeypatch.setattr("os.remove", lambda path: None)
    
    # Mock open locally inside backend.services.youtube_ingester
    mock_file = mock.mock_open(read_data=b"dummy_audio_bytes")
    
    conn = MockConnection()
    with mock.patch("backend.services.youtube_ingester.open", mock_file):
        item_id = await ingest_youtube("https://www.youtube.com/watch?v=12345", 42, conn)
    
    assert item_id == 101
    
    # Verify DB queries
    executed_queries = conn.cursor_inst.executed
    assert len(executed_queries) == 1
    insert_query, params = executed_queries[0]
    assert "INSERT INTO items" in insert_query
    assert params[0] == 42 # user_id
    assert params[1] == "https://www.youtube.com/watch?v=12345" # url
    assert "Mocked Video Summary" in params[3] # summary
    assert params[4] == "Test YouTube Video" # title

@pytest.mark.asyncio
async def test_youtube_transcript_fallback_happy_path(monkeypatch, mock_dependencies):
    """Test that when audio download fails, the pipeline falls back to youtube-transcript-api."""
    mock_info = {
        "title": "Test YouTube Video",
        "duration": 300,
    }
    
    class MockYoutubeDL:
        def __init__(self, opts=None):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def extract_info(self, url, download=False):
            return mock_info
        def download(self, urls):
            raise RuntimeError("403 Forbidden Sim")
            
    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYoutubeDL)
    monkeypatch.setattr("os.path.exists", lambda path: False)
    
    conn = MockConnection()
    item_id = await ingest_youtube("https://www.youtube.com/watch?v=12345", 42, conn)
    
    assert item_id == 101
    
    # Verify DB queries
    executed_queries = conn.cursor_inst.executed
    assert len(executed_queries) == 1
    insert_query, params = executed_queries[0]
    assert "INSERT INTO items" in insert_query
    assert params[0] == 42
    assert "Mocked Video Summary" in params[3]

@pytest.mark.asyncio
async def test_youtube_ingestion_failure_bookmark_fallback(monkeypatch, mock_dependencies):
    """Test that when both audio download and transcript api fail, it falls back to the bookmark tier."""
    mock_info = {
        "title": "Test YouTube Video",
        "duration": 300,
    }
    
    class MockYoutubeDL:
        def __init__(self, opts=None):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def extract_info(self, url, download=False):
            return mock_info
        def download(self, urls):
            raise RuntimeError("403 Forbidden Sim")
            
    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYoutubeDL)
    monkeypatch.setattr("os.path.exists", lambda path: False)
    
    # Mock youtube-transcript-api to fail
    class MockYouTubeTranscriptApi:
        def list(self, video_id):
            raise RuntimeError("TranscriptsDisabled Sim")
            
    monkeypatch.setattr("youtube_transcript_api.YouTubeTranscriptApi", MockYouTubeTranscriptApi)
    
    conn = MockConnection()
    item_id = await ingest_youtube("https://www.youtube.com/watch?v=12345", 42, conn)
    
    assert item_id == 101
    
    # Verify DB queries (inserted as bookmark)
    executed_queries = conn.cursor_inst.executed
    assert len(executed_queries) == 1
    insert_query, params = executed_queries[0]
    assert "INSERT INTO items" in insert_query
    assert params[0] == 42
    assert "Saved as a placeholder bookmark" in params[3] # bookmark summary
    assert "Bookmark: Test YouTube Video" == params[4] # bookmark title
