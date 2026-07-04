import pytest
from backend.services.pdf_ingester import chunk_text, get_summarization_context

def test_chunk_text():
    text = "Sentence one. " * 100 + "Sentence two. " * 100
    chunks = chunk_text(text, chunk_size_words=50)
    assert len(chunks) > 1

def test_get_summarization_context():
    short_text = "This is a short text document."
    assert get_summarization_context(short_text, max_chars=1000) == short_text

    long_text = "A" * 100000
    sampled = get_summarization_context(long_text, max_chars=60000)
    assert "[... TEXT TRUNCATED FOR CONTEXT LIMITS ...]" in sampled
    assert len(sampled) < 100000
