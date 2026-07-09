import re
import math
import logging
import asyncio
import unicodedata
from typing import List, Dict, Any, Tuple
from backend.config import settings
from backend.services.nlp import get_spacy_sentencizer

logger = logging.getLogger("chunker")

# Thread-safe global model reference
_local_chunk_model = None

async def embed_text_batch(texts: List[str]) -> List[List[float]]:
    """
    Generates BGE embeddings for a batch of strings locally.
    Used for sentence-level semantic comparison in the chunker.
    """
    if not texts:
        return []
        
    if settings.ENV == "test":
        val = 1.0 / (384 ** 0.5)
        return [[val] * 384 for _ in texts]

    if getattr(settings, "EMBEDDING_PROVIDER", "local") == "remote":
        from backend.services.remote_ai_client import generate_remote_embedding_batch
        try:
            return await generate_remote_embedding_batch(texts)
        except Exception as e:
            logger.error("Remote batch embedding failed: %s. Falling back.", e)

    global _local_chunk_model
    try:
        from fastembed import TextEmbedding
        if _local_chunk_model is None or not isinstance(_local_chunk_model, TextEmbedding):
            logger.info("Initializing local FastEmbed TextEmbedding('BAAI/bge-small-en-v1.5') for chunking...")
            _local_chunk_model = TextEmbedding("BAAI/bge-small-en-v1.5")
            
        loop = asyncio.get_running_loop()
        embeddings_iterator = await loop.run_in_executor(None, lambda: list(_local_chunk_model.embed(texts)))
        return [[float(x) for x in emb] for emb in embeddings_iterator]
    except ImportError:
        pass
    except Exception as e:
        logger.error("Failed to generate batch embedding via FastEmbed in chunker: %s", e)

    # Fallback to SentenceTransformer
    try:
        from sentence_transformers import SentenceTransformer
        if _local_chunk_model is None or not hasattr(_local_chunk_model, "encode"):
            logger.info("Initializing local SentenceTransformer('BAAI/bge-small-en-v1.5') for chunking...")
            _local_chunk_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, lambda: _local_chunk_model.encode(texts).tolist())
        return embeddings
    except Exception as e:
        logger.error("Failed to generate batch embedding via SentenceTransformer in chunker: %s", e)
        
    # Final fallback to mock vectors
    val = 1.0 / (384 ** 0.5)
    return [[val] * 384 for _ in texts]

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes the cosine similarity between two 1D vector lists."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def split_into_sections(text: str) -> List[Dict[str, str]]:
    """
    Splits document text into logical sections based on headings and page breaks.
    """
    lines = text.splitlines()
    sections = []
    current_section_lines = []
    current_section_title = "Intro"

    # Match Markdown headings (e.g. # H1, ## H2), page breaks, or horizontal rules
    heading_pattern = re.compile(
        r"^(#{1,6}\s+.*|\[Page\s+\d+\]|\[Scanned Page\s+\d+.*\]|[\-\*_]{3,}\s*)$", 
        re.IGNORECASE
    )

    for line in lines:
        if heading_pattern.match(line.strip()):
            if current_section_lines:
                sections.append({
                    "title": current_section_title,
                    "content": "\n".join(current_section_lines).strip()
                })
            current_section_lines = [line]
            current_section_title = line.strip()
        else:
            current_section_lines.append(line)

    if current_section_lines:
        sections.append({
            "title": current_section_title,
            "content": "\n".join(current_section_lines).strip()
        })
        
    return [s for s in sections if s["content"].strip()]

async def semantic_chunk_text(text: str) -> List[str]:
    """
    Splits a document text into semantic chunks, respecting logical heading boundaries.
    """
    if not text or not text.strip():
        return []

    sections = split_into_sections(text)
    all_chunks = []

    for section in sections:
        content = section["content"]
        
        # Split into sentences using spaCy
        nlp = get_spacy_sentencizer()
        doc = nlp(content)
        
        sentences_with_counts: List[Tuple[str, int]] = []
        for sent in doc.sents:
            s_text = sent.text.strip()
            if not s_text:
                continue
            words = s_text.split()
            if not words:
                continue
            sentences_with_counts.append((s_text, len(words)))

        if not sentences_with_counts:
            continue

        # If the entire section is small, keep it intact as a single small chunk
        total_section_words = sum(s[1] for s in sentences_with_counts)
        if total_section_words <= settings.CHUNK_MAX_WORDS:
            all_chunks.append(" ".join(s[0] for s in sentences_with_counts))
            continue

        # Batch embed all sentences in the section to evaluate semantic similarity
        sentence_texts = [s[0] for s in sentences_with_counts]
        embeddings: List[List[float]] = []
        
        # Batch in sizes of 128 to prevent memory/CPU spikes
        for i in range(0, len(sentence_texts), 128):
            batch = sentence_texts[i:i+128]
            batch_embeddings = await embed_text_batch(batch)
            embeddings.extend(batch_embeddings)

        # Compute cosine similarities between adjacent sentences
        similarities = []
        for idx in range(len(embeddings) - 1):
            sim = cosine_similarity(embeddings[idx], embeddings[idx + 1])
            similarities.append(sim)

        # Group sentences into chunks using semantic similarity splits and size boundaries
        section_chunks = []
        current_chunk: List[Tuple[str, int]] = []
        current_word_count = 0

        for idx, (sent_text, word_count) in enumerate(sentences_with_counts):
            current_chunk.append((sent_text, word_count))
            current_word_count += word_count

            is_semantic_boundary = False
            if idx < len(sentences_with_counts) - 1:
                if similarities[idx] < settings.SEMANTIC_SPLIT_THRESHOLD:
                    is_semantic_boundary = True

            # Determine split boundaries
            exceeded_max = current_word_count >= settings.CHUNK_MAX_WORDS
            satisfied_min = current_word_count >= settings.CHUNK_MIN_WORDS

            should_split = False
            if exceeded_max:
                should_split = True
            elif is_semantic_boundary and satisfied_min:
                should_split = True

            if should_split and idx < len(sentences_with_counts) - 1:
                chunk_str = " ".join([s[0] for s in current_chunk])
                section_chunks.append(chunk_str)

                # Configure overlap boundary (never crossing the heading/section start)
                overlap_len = min(settings.CHUNK_OVERLAP_SENTENCES, len(current_chunk))
                overlap_sents = current_chunk[-overlap_len:] if overlap_len > 0 else []
                
                current_chunk = list(overlap_sents)
                current_word_count = sum(s[1] for s in current_chunk)

        if current_chunk:
            chunk_str = " ".join([s[0] for s in current_chunk])
            section_chunks.append(chunk_str)

        all_chunks.extend(section_chunks)

    return all_chunks
