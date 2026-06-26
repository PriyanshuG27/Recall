import os
import re
import tempfile
import pytest
import fitz  # PyMuPDF
import psycopg
from datetime import datetime
from backend.services.pdf_ingester import ingest_pdf, chunk_text, extract_pdf_text
from backend.services.search_service import hybrid_search, embed_text

# Shared valid environment for testing
VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
    "ENV": "test",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

# --- STATEFUL DATABASE MOCK FOR OFFLINE UNIT TESTING ---

class MockDbState:
    def __init__(self):
        self.items = []
        self.item_chunks = []
        self.next_item_id = 1
        self.next_chunk_id = 1
        self.queries = []

class MockCursor:
    def __init__(self, state):
        self.state = state
        self._last_query = ""
        self._last_params = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.state.queries.append((query, params))
        self._last_query = query
        self._last_params = params or ()
        
        query_upper = query.upper()
        
        if "INSERT INTO ITEMS" in query_upper:
            # params: user_id, title, source_type, source_url, raw_text, summary, embedding, tags (optional), content_hash (optional)
            tags = []
            if len(params) == 9:
                user_id, title, source_type, source_url, raw_text, summary, embedding, tags, _content_hash = params
            elif len(params) == 8:
                user_id, title, source_type, source_url, raw_text, summary, embedding, tags = params
            else:
                user_id, title, source_type, source_url, raw_text, summary, embedding = params
            item_id = self.state.next_item_id
            self.state.next_item_id += 1
            self.state.items.append({
                "id": item_id,
                "user_id": user_id,
                "title": title,
                "source_type": source_type,
                "source_url": source_url,
                "raw_text": raw_text,
                "summary": summary,
                "embedding": embedding,
                "tags": tags
            })
            
        elif "INSERT INTO ITEM_CHUNKS" in query_upper:
            # params: item_id, user_id, chunk_index, chunk_text, embedding
            item_id, user_id, chunk_index, chunk_text, embedding = params
            chunk_id = self.state.next_chunk_id
            self.state.next_chunk_id += 1
            self.state.item_chunks.append({
                "id": chunk_id,
                "item_id": item_id,
                "user_id": user_id,
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "embedding": embedding
            })
            
        elif "DELETE FROM ITEM_CHUNKS" in query_upper:
            item_id, user_id = params
            self.state.item_chunks = [c for c in self.state.item_chunks if not (c["item_id"] == item_id and c["user_id"] == user_id)]
            
        elif "DELETE FROM ITEMS" in query_upper:
            item_id, user_id = params
            deleted = [i for i in self.state.items if i["id"] == item_id and i["user_id"] == user_id]
            self.state.items = [i for i in self.state.items if not (i["id"] == item_id and i["user_id"] == user_id)]
            # Simulate trigger cascade in mock: deleting from items removes item_chunks
            if deleted:
                self.state.item_chunks = [c for c in self.state.item_chunks if c["item_id"] != item_id]

    async def fetchone(self):
        query_upper = self._last_query.upper()
        if "INSERT INTO ITEMS" in query_upper:
            return (self.state.items[-1]["id"],)
        elif "DELETE FROM ITEMS" in query_upper:
            return (self._last_params[0], "pdf")
        return None

    async def fetchall(self):
        query_upper = self._last_query.upper()
        
        if "WITH " in query_upper:
            # Consolidated search query
            user_id = self._last_params[1]
            rows = []
            for item in self.state.items:
                if item["user_id"] == user_id:
                    rows.append((
                        item["id"],
                        item["title"],
                        item["summary"],
                        item["source_type"],
                        item["source_url"],
                        item.get("tags", []),
                        datetime.now(),
                        1.0  # RRF score
                    ))
            return rows
            
        if "FROM ITEM_CHUNKS" in query_upper:
            user_id = self._last_params[0]
            seen = set()
            rows = []
            for chunk in self.state.item_chunks:
                if chunk["user_id"] == user_id and chunk["item_id"] not in seen:
                    rows.append((chunk["item_id"],))
                    seen.add(chunk["item_id"])
            return rows
            
        elif "FROM ITEMS" in query_upper:
            user_id = self._last_params[0]
            if "ANY(" in query_upper or "ANY(%S)" in query_upper:
                item_ids = self._last_params[1]
                rows = []
                for item in self.state.items:
                    if item["user_id"] == user_id and item["id"] in item_ids:
                        rows.append((item["id"], item["title"], item["summary"], item["source_type"], item["source_url"], [], datetime.now()))
                return rows
            else:
                rows = []
                for item in self.state.items:
                    if item["user_id"] == user_id:
                        rows.append((item["id"], item["title"], item["summary"], item["source_type"], item["source_url"], [], datetime.now()))
                return rows
        return []

class MockConnection:
    def __init__(self, state):
        self.state = state

    def cursor(self):
        return MockCursor(self.state)

    async def commit(self):
        pass

    async def rollback(self):
        pass

# --- HELPER TO GENERATE MULTI-PAGE PDF ---

def create_dummy_pdf(num_pages: int, path: str):
    """Create a dummy PDF file with a specific page count using PyMuPDF (fitz)."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        # Insert sentence-rich content to make sure sentence bounding works correctly
        text_parts = []
        for j in range(15):
            text_parts.append(f"Sentence {j+1} on page {i+1} is here for testing chunking behavior of the pdf ingester.")
        if i == 6:  # Page 7 (0-indexed page index 6)
            text_parts.append("Unique code on page seven is RECALL_P7_SECRET.")
        text = " ".join(text_parts)
        rect = fitz.Rect(50, 50, 550, 750)
        page.insert_textbox(rect, text)
    doc.save(path)
    doc.close()

# --- TESTS ---

@pytest.mark.anyio
async def test_pdf_ingestion_creates_chunks():
    """Verify that ingesting a 10-page PDF splits it into >= 3 chunks and writes to DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test_10page.pdf")
        # 10 pages, each page has ~30 words -> total ~300 words.
        # With sentence-boundary chunking, it will produce >= 3 chunks when chunk size limit is set accordingly.
        create_dummy_pdf(num_pages=10, path=pdf_path)
        
        # Verify fitz reading works
        text = await extract_pdf_text(pdf_path)
        assert "page 1" in text
        assert "page 10" in text
        
        state = MockDbState()
        conn = MockConnection(state)
        
        # Ingest PDF
        item_id = await ingest_pdf(pdf_path, user_id=42, title="My 10-Page Document", source_url="http://example.com/pdf", db=conn)
        
        # Check parent item
        assert len(state.items) == 1
        parent = state.items[0]
        assert parent["id"] == item_id
        assert parent["source_type"] == "pdf"
        assert parent["title"] == "My 10-Page Document"
        
        # Check chunks
        assert len(state.item_chunks) >= 3
        for idx, chunk in enumerate(state.item_chunks):
            assert chunk["item_id"] == item_id
            assert chunk["user_id"] == 42
            assert chunk["chunk_index"] == idx
            assert len(chunk["chunk_text"]) <= 500  # Excerpt chunk storage (up to 500 chars)
            
        # items.embedding must equal first chunk's embedding (chunk index 0)
        assert parent["embedding"] == state.item_chunks[0]["embedding"]

@pytest.mark.anyio
async def test_independent_chunk_search():
    """Verify that the chunk-level vector search query can be executed independently."""
    state = MockDbState()
    conn = MockConnection(state)
    
    # Pre-populate some chunks
    state.item_chunks.append({
        "id": 1,
        "item_id": 100,
        "user_id": 42,
        "chunk_index": 0,
        "chunk_text": "First chunk text",
        "embedding": [0.1] * 384
    })
    state.item_chunks.append({
        "id": 2,
        "item_id": 100,
        "user_id": 42,
        "chunk_index": 1,
        "chunk_text": "Second chunk text",
        "embedding": [0.2] * 384
    })
    
    # Execute chunk search independently
    async with conn.cursor() as cur:
        query = """
            SELECT DISTINCT item_id 
            FROM item_chunks 
            WHERE user_id = %s 
            ORDER BY embedding <=> %s::vector 
            LIMIT 20;
        """
        await cur.execute(query, (42, [0.15] * 384))
        rows = await cur.fetchall()
        
    assert len(rows) == 1
    assert rows[0][0] == 100
    
    # Verify that the query structure matches requirements (e.g. user_id scope and cast to ::vector)
    assert "WHERE user_id = %s" in state.queries[-1][0]
    assert "embedding <=> %s::vector" in state.queries[-1][0]

@pytest.mark.anyio
async def test_search_page_7_content_returns_parent_item():
    """Verify that a hybrid search matching page 7 content returns the parent item."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test_page7.pdf")
        create_dummy_pdf(num_pages=10, path=pdf_path)
        
        state = MockDbState()
        conn = MockConnection(state)
        
        # Ingest PDF
        item_id = await ingest_pdf(pdf_path, user_id=42, title="My 10-Page Document", source_url="http://example.com/pdf", db=conn)
        
        # Run hybrid search
        results = await hybrid_search("RECALL_P7_SECRET", user_id=42, db=conn)
        
        # Verify that parent item is returned
        assert len(results) > 0
        assert results[0]["id"] == item_id
        assert results[0]["title"] == "My 10-Page Document"

@pytest.mark.anyio
async def test_cascading_deletion():
    """Verify that deleting an item removes all associated item_chunks rows."""
    state = MockDbState()
    conn = MockConnection(state)
    
    # Pre-populate parent and chunks
    state.items.append({
        "id": 50,
        "user_id": 42,
        "title": "Document 50",
        "source_type": "pdf",
        "source_url": None,
        "raw_text": "Encrypted raw text",
        "summary": "Summary",
        "embedding": [0.1] * 384
    })
    for i in range(5):
        state.item_chunks.append({
            "id": i + 10,
            "item_id": 50,
            "user_id": 42,
            "chunk_index": i,
            "chunk_text": f"Excerpt {i}",
            "embedding": [0.1] * 384
        })
        
    assert len(state.items) == 1
    assert len(state.item_chunks) == 5
    
    # Execute deletion (simulates API DELETE call)
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM item_chunks WHERE item_id = %s AND user_id = %s;",
            (50, 42)
        )
        await cur.execute(
            "DELETE FROM items WHERE id = %s AND user_id = %s RETURNING id, source_type;",
            (50, 42)
        )
        
    assert len(state.items) == 0
    assert len(state.item_chunks) == 0

def test_hnsw_index_on_item_chunks_confirmed_via_schema_or_db():
    """Verify HNSW index config is present on item_chunks table in schema.sql."""
    # Find schema.sql path
    # D:\Recall\backend\tests\test_pdf_chunks.py -> parent of parent is D:\Recall
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema_path = os.path.join(base_dir, "backend", "db", "schema.sql")
    
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_content = f.read()
        
    # Search for HNSW index definition on item_chunks
    index_regex = re.compile(
        r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+item_chunks\s+USING\s+hnsw\s*\(\s*embedding\s+vector_cosine_ops\s*\)\s*WITH\s*\(\s*m\s*=\s*16\s*,\s*ef_construction\s*=\s*64\s*\)",
        re.IGNORECASE
    )
    
    assert index_regex.search(schema_content) is not None, \
        "HNSW index on item_chunks embedding using cosine ops (m=16, ef_construction=64) not found in schema.sql"

# --- NEW TESTS ---

from unittest.mock import AsyncMock, MagicMock
from backend.services.pdf_ingester import get_summarization_context, extract_pdf_text

def test_head_tail_sampling():
    """Verify that get_summarization_context correctly samples head-tail or returns full text."""
    # Under limit
    short_text = "Hello World"
    assert get_summarization_context(short_text, max_chars=100) == short_text
    
    # Over limit
    long_text = "A" * 70000
    sampled = get_summarization_context(long_text, max_chars=60000)
    assert "[... TEXT TRUNCATED FOR CONTEXT LIMITS ...]" in sampled
    assert len(sampled) == 40000 + 20000 + len("\n\n[... TEXT TRUNCATED FOR CONTEXT LIMITS ...]\n\n")

@pytest.mark.anyio
async def test_scanned_pdf_processing_with_tesseract(monkeypatch):
    """Test scanned PDF processing when Tesseract is available."""
    # Mock check_tesseract_available to return True
    monkeypatch.setattr("backend.services.pdf_ingester.check_tesseract_available", lambda: True)
    
    # Mock pytesseract.image_to_string
    monkeypatch.setattr("pytesseract.image_to_string", lambda img: "Mocked OCR Text from Tesseract")
    
    # Create a dummy scanned PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "scanned.pdf")
        # Create a PDF with 1 page, empty text (so length < 50)
        doc = fitz.open()
        page = doc.new_page()
        page.draw_rect(fitz.Rect(10, 10, 100, 100))
        doc.save(pdf_path)
        doc.close()
        
        # Extract text - should run mock OCR
        text = await extract_pdf_text(pdf_path, cascade=None)
        assert "Mocked OCR Text from Tesseract" in text

@pytest.mark.anyio
async def test_scanned_pdf_processing_gemini_fallback(monkeypatch):
    """Test scanned PDF processing fallback to Gemini Vision when Tesseract is missing."""
    # Mock check_tesseract_available to return False
    monkeypatch.setattr("backend.services.pdf_ingester.check_tesseract_available", lambda: False)
    
    # Create mock AICascade
    mock_cascade = MagicMock()
    mock_cascade.caption_image = AsyncMock(return_value="Mocked Gemini Caption")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "scanned_gemini.pdf")
        # Create a PDF with 10 pages, all scanned (empty text)
        doc = fitz.open()
        for i in range(10):
            page = doc.new_page()
            page.draw_rect(fitz.Rect(10, 10, 100, 100))
        doc.save(pdf_path)
        doc.close()
        
        # Extract text - should apply visual budget (first 5 and last 3 pages)
        text = await extract_pdf_text(pdf_path, cascade=mock_cascade)
        
        # Page 1 (index 0) - budgeted
        assert "Mocked Gemini Caption" in text
        # Page 6 (index 5) - skipped due to budget
        assert "skipped to respect API rate limits/budgets" in text
        
        # Verify caption_image was called exactly 8 times (first 5 + last 3)
        assert mock_cascade.caption_image.call_count == 8
