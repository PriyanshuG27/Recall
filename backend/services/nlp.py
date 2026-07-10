import os
import re
import logging
import asyncio

logger = logging.getLogger(__name__)

class MockSpan:
    def __init__(self, text: str):
        self.text = text

class MockDoc:
    def __init__(self, text: str, sentences: list = None):
        self.text = text
        if sentences is not None:
            self.sents = [MockSpan(s) for s in sentences]
        else:
            if not text:
                self.sents = []
                return
            # Regex split on sentence boundaries
            sents_split = re.split(r'(?<=[.!?])\s+(?=[A-Za-z0-9])', text)
            self.sents = [MockSpan(s.strip()) for s in sents_split if s.strip()]

class RegexSentencizer:
    def __call__(self, text: str) -> MockDoc:
        return MockDoc(text)

class RemoteSentencizer:
    def __call__(self, text: str) -> MockDoc:
        from backend.services.remote_ai_client import generate_remote_sentence_split
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(generate_remote_sentence_split(text)))
                    sentences = future.result()
            else:
                sentences = loop.run_until_complete(generate_remote_sentence_split(text))
            return MockDoc(text, sentences)
        except Exception as e:
            logger.error("Remote sentence splitting failed: %s. Falling back to local regex sentencizer.", e)
            return MockDoc(text)

_nlp_instance = None

def get_spacy_sentencizer():
    """Returns the shared sentencizer instance based on configuration."""
    global _nlp_instance
    if _nlp_instance is None:
        from backend.config import settings
        provider = getattr(settings, "SENTENCE_SPLITTER", "spacy")
        if provider == "regex":
            logger.info("Using lightweight RegexSentencizer (bypassing spaCy import)...")
            _nlp_instance = RegexSentencizer()
        elif provider == "remote":
            logger.info("Using RemoteSentencizer (bypassing spaCy import)...")
            _nlp_instance = RemoteSentencizer()
        else:
            try:
                logger.info("Initializing spaCy English sentencizer...")
                import spacy
                nlp = spacy.blank("en")
                nlp.add_pipe("sentencizer")
                _nlp_instance = nlp
            except ImportError:
                logger.warning("spaCy is not installed. Falling back to lightweight RegexSentencizer.")
                _nlp_instance = RegexSentencizer()
    return _nlp_instance

