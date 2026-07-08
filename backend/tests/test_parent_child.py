import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import spacy

from backend.config import settings
from backend.services.pdf_ingester import chunk_text
from backend.services.search_service import hybrid_search

def test_spacy_sentencizer_abbreviations():
    """Verify that the shared spaCy sentencizer doesn't split sentences on common abbreviations."""
    from backend.services.nlp import get_spacy_sentencizer
    nlp = get_spacy_sentencizer()
    text = "Dr. Smith went to the U.S. and spent 3.14 million dollars, i.e., a lot of money. He returned the next day."
    doc = nlp(text)
    sentences = list(doc.sents)
    # Should only split into 2 sentences: one for Dr. Smith... and one for He returned...
    assert len(sentences) == 2
    assert "Dr. Smith" in sentences[0].text
    assert "He returned" in sentences[1].text

def test_adaptive_sentence_aware_chunking():
    """Verify chunk_text respects target, min, max word boundaries and overlap configurations."""
    # 5 sentences, each has 10 words -> 50 words total
    text = (
        "Sentence one has exactly ten words in this dummy text. "
        "Sentence two has exactly ten words in this dummy text. "
        "Sentence three has exactly ten words in this dummy text. "
        "Sentence four has exactly ten words in this dummy text. "
        "Sentence five has exactly ten words in this dummy text."
    )
    
    # Test case 1: Target = 20 words, Min = 10, Max = 30, Overlap = 1 sentence (10 words)
    chunks = chunk_text(text, target_words=20, min_words=10, max_words=30, overlap_sentences=1)
    
    assert len(chunks) == 4
    assert chunks[0] == "Sentence one has exactly ten words in this dummy text. Sentence two has exactly ten words in this dummy text."
    assert chunks[1] == "Sentence two has exactly ten words in this dummy text. Sentence three has exactly ten words in this dummy text."
    assert chunks[2] == "Sentence three has exactly ten words in this dummy text. Sentence four has exactly ten words in this dummy text."
    assert chunks[3] == "Sentence four has exactly ten words in this dummy text. Sentence five has exactly ten words in this dummy text."

    # Test case 2: Target = 35 words, Min = 15. The remaining chunk will be small, so it should merge with previous.
    chunks_merged = chunk_text(text, target_words=30, min_words=25, max_words=50, overlap_sentences=0)
    # Sentence 1-3 is 30 words (Chunk 0). Sentence 4-5 is 20 words (remaining).
    # Since remaining 20 words < min_words (25), it should merge into Chunk 0.
    assert len(chunks_merged) == 1
    assert "Sentence five" in chunks_merged[0]

@pytest.mark.anyio
async def test_hybrid_search_context_expansion():
    """Verify that hybrid_searchGroups matched child chunks, runs single join query, and dynamically expands context."""
    # Mock items return row from hybrid_search database
    now = datetime.now(timezone.utc)
    mock_rows = [
        # id, title, summary, source_type, source_url, tags, created_at, score, raw_text, chunk_text, chunk_index
        (101, "FastAPI guide", "FastAPI web dev", "text", "http://example.com", ["web"], now, 0.85, None, "Sentence three matched child chunk here.", 12)
    ]
    
    # Mock sibling chunks fetched from database query
    mock_sibling_rows = [
        # item_id, chunk_index, chunk_text
        (101, 10, "Sentence one context prefix."),
        (101, 11, "Sentence two context prefix."),
        (101, 12, "Sentence three matched child chunk here."),
        (101, 13, "Sentence four context suffix."),
        (101, 14, "Sentence five context suffix.")
    ]

    # Mock cursor
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    # First fetchall returns the candidate matches, second returns the sibling chunks
    mock_cursor.fetchall = AsyncMock(side_effect=[mock_rows, mock_sibling_rows])
    
    # Mock connection
    mock_db = MagicMock()
    mock_db.cursor = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_cursor)))

    # Mock settings parameters
    with patch("backend.services.search_service.embed_text", new=AsyncMock(return_value=[0.1]*384)), \
         patch.object(settings, "ENABLE_RERANKING", False), \
         patch.object(settings, "PARENT_TARGET_WORDS", 30), \
         patch.object(settings, "MAX_EXPANDED_WORDS", 40):
         
        results = await hybrid_search("query text", 42, mock_db)
        
        # Verify database calls
        assert len(results) == 1
        winner = results[0]
        
        # Verify matched_chunk_text and expanded_context are present
        assert winner["matched_chunk_text"] == "Sentence three matched child chunk here."
        assert "expanded_context" in winner
        
        # Verify expanded_context contains matched chunk + expanded siblings
        expanded = winner["expanded_context"]
        assert "Sentence three matched child chunk" in expanded
        assert "Sentence two context" in expanded
        assert "Sentence four context" in expanded
        
        # Verify safety cap (40 words) is respected
        word_count = len(expanded.split())
        assert word_count <= 40
