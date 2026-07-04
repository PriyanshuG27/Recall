import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
from psycopg import AsyncConnection

from backend.config import settings

logger = logging.getLogger(__name__)

_local_model = None

async def embed_text(text: str) -> List[float]:
    """
    Generate a 384-dimensional vector embedding for the query.
    If in testing mode, returns a mock vector.
    Otherwise, calls the Modal serverless GPU endpoint, falling back to local sentence-transformers
    (if installed), then to Gemini embedding, and finally a mock vector.
    Results are cached in Redis.
    """
    if settings.ENV == "test":
        # Return a normalized mock 384-dim vector for testing/local development
        val = 1.0 / (384 ** 0.5)
        return [val] * 384

    from backend.services.redis_client import redis
    import json

    cache_key = f"embed:{text}"
    try:
        cached_embed_str = await redis.get(cache_key)
        if cached_embed_str:
            cached_embed = json.loads(cached_embed_str)
            if isinstance(cached_embed, list) and len(cached_embed) == 384:
                logger.info("Embedding cache HIT for text of length %d", len(text))
                return cached_embed
    except Exception as e:
        logger.warning("Failed to fetch embedding from Redis cache: %s", e)

    logger.info("Embedding cache MISS for text of length %d. Generating new embedding...", len(text))
    embedding = await _generate_embedding_uncached(text)

    try:
        # Cache for 7 days (604800 seconds)
        await redis.setex(cache_key, 604800, json.dumps(embedding))
    except Exception as e:
        logger.warning("Failed to write embedding to Redis cache: %s", e)

    return embedding


async def _generate_embedding_uncached(text: str) -> List[float]:
    """Generate the embedding from remote API or local model without caching."""
    global _local_model

    # 1. Try Modal if a real API token is configured
    if settings.MODAL_API_TOKEN and not settings.MODAL_API_TOKEN.startswith("ak-mock"):
        try:
            logger.info("Attempting embedding generation via Modal...")
            # Call the Modal MiniLM endpoint
            url = "https://pri27--minilm-embed.modal.run/embed"
            headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"text": text}, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) == 384:
                        logger.info("Successfully generated embedding via Modal API.")
                        return data
                else:
                    logger.warning("Modal embedding returned status code %d", response.status_code)
        except Exception as e:
            logger.error("Failed to generate embedding via Modal: %s", e)

    # 2. Try Local FastEmbed (ONNX - ultra-lightweight ~45MB RAM for Koyeb Free Tier)
    try:
        from fastembed import TextEmbedding
        if _local_model is None or not isinstance(_local_model, TextEmbedding):
            logger.info("Initializing local FastEmbed TextEmbedding('BAAI/bge-small-en-v1.5')...")
            _local_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        
        logger.info("Attempting local embedding generation via FastEmbed ONNX...")
        import asyncio
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, lambda: list(_local_model.embed([text])))
        if embeddings and len(embeddings[0]) == 384:
            logger.info("Successfully generated embedding via local FastEmbed (ONNX).")
            return [float(x) for x in embeddings[0]]
    except ImportError:
        pass
    except Exception as e:
        logger.error("Failed to generate embedding via FastEmbed: %s", e)

    # 2.5 Try Local SentenceTransformer (if installed)
    try:
        from sentence_transformers import SentenceTransformer
        if _local_model is None or not hasattr(_local_model, "encode"):
            logger.info("Initializing local SentenceTransformer('all-MiniLM-L6-v2')...")
            _local_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        logger.info("Attempting local embedding generation via SentenceTransformer...")
        import asyncio
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, lambda: _local_model.encode(text).tolist())
        if isinstance(embedding, list) and len(embedding) == 384:
            logger.info("Successfully generated embedding via local SentenceTransformer.")
            return embedding
    except ImportError:
        pass
    except Exception as e:
        logger.error("Failed to generate local embedding: %s", e)

    # 3. Try Hugging Face Serverless Inference API if HF_TOKEN is configured
    if settings.HF_TOKEN and not settings.HF_TOKEN.startswith("mock") and settings.HF_TOKEN != "":
        try:
            logger.info("Attempting embedding generation via Hugging Face Inference API...")
            url = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
            headers = {"Authorization": f"Bearer {settings.HF_TOKEN}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"inputs": text}, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        if len(data) == 384:
                            logger.info("Successfully generated embedding via Hugging Face Inference API.")
                            return data
                        elif len(data) > 0 and isinstance(data[0], list) and len(data[0]) == 384:
                            logger.info("Successfully generated embedding via Hugging Face Inference API.")
                            return data[0]
                else:
                    logger.warning("Hugging Face embedding returned status code %d: %s", response.status_code, response.text)
        except Exception as e:
            logger.error("Failed to generate embedding via Hugging Face Inference API: %s", e)

    # 4. Fallback to Gemini if valid API key is present
    if settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            logger.warning("Failing back to Gemini embedding model. WARNING: This will cause vector space misalignment with MiniLM embeddings!")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "model": "models/gemini-embedding-2",
                "content": {
                    "parts": [{"text": text}]
                },
                "outputDimensionality": 384
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    res_data = response.json()
                    embedding = res_data.get("embedding", {}).get("values", [])
                    if isinstance(embedding, list) and len(embedding) == 384:
                        logger.info("Successfully generated embedding via Gemini fallback.")
                        return embedding
                else:
                    logger.warning("Gemini embedding returned status code %d: %s", response.status_code, response.text)
        except Exception as e:
            logger.error("Failed to generate embedding via Gemini fallback: %s", e)

    logger.warning("All embedding generation methods failed. Returning fallback mock vector.")
    val = 1.0 / (384 ** 0.5)
    return [val] * 384



async def hybrid_search(query: str, user_id: int, db: AsyncConnection) -> List[Dict[str, Any]]:
    """
    Perform a hybrid search using pgvector (HNSW cosine distance) on both items and item_chunks,
    and pg_trgm (GIN trigram similarity) on items.
    Combines results using Reciprocal Rank Fusion (RRF) and returns the top 5 matches.
    """
    # Step 1: Generate query embedding
    query_embedding = await embed_text(query)

    consolidated_query = """
        WITH direct_vector AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) as rank
            FROM items
            WHERE user_id = %s AND (embedding <=> %s::vector) < 0.8
            ORDER BY embedding <=> %s::vector
            LIMIT 20
        ),
        chunk_vector AS (
            SELECT item_id AS id, ROW_NUMBER() OVER (ORDER BY min_row_num) as rank
            FROM (
                SELECT item_id, MIN(row_num) as min_row_num
                FROM (
                    SELECT item_id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) as row_num
                    FROM item_chunks
                    WHERE user_id = %s AND (embedding <=> %s::vector) < 0.8
                    LIMIT 50
                ) sub
                GROUP BY item_id
            ) sub2
            ORDER BY min_row_num
            LIMIT 20
        ),
        combined_vector_ids AS (
            SELECT id, MIN(val_rank) AS final_rank
            FROM (
                SELECT id, rank AS val_rank FROM direct_vector
                UNION ALL
                SELECT id, rank + 20 AS val_rank FROM chunk_vector
            ) u
            GROUP BY id
        ),
        ranked_vector AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY final_rank) as rank
            FROM combined_vector_ids
        ),
        text_search AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY similarity(summary, %s) DESC) as rank
            FROM items
            WHERE user_id = %s AND summary %% %s
            ORDER BY similarity(summary, %s) DESC
            LIMIT 20
        ),
        rrf_scores AS (
            SELECT 
                COALESCE(v.id, t.id) as id,
                COALESCE(1.0 / (v.rank + 60), 0.0) + COALESCE(1.0 / (t.rank + 60), 0.0) as rrf_score
            FROM ranked_vector v
            FULL OUTER JOIN text_search t ON v.id = t.id
        )
        SELECT 
            i.id, i.title, i.summary, i.source_type, i.source_url, i.tags, i.created_at,
            r.rrf_score
        FROM rrf_scores r
        JOIN items i ON r.id = i.id
        WHERE i.user_id = %s
        ORDER BY r.rrf_score DESC
        LIMIT 5;
    """

    query_params = (
        query_embedding, user_id, query_embedding, query_embedding,
        query_embedding, user_id, query_embedding,
        query, user_id, query, query,
        user_id
    )

    async with db.cursor() as cur:
        await cur.execute(consolidated_query, query_params)
        rows = await cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "source_type": r[3],
                "source_url": r[4],
                "tags": r[5] if r[5] is not None else [],
                "created_at": r[6],
                "score": float(r[7]),
            })

    return results


async def rag_semantic_search(query: str, user_id: int, db: AsyncConnection, limit: int = 12) -> List[Dict[str, Any]]:
    """
    Perform a pure semantic search using pgvector (HNSW cosine similarity)
    on the user's items for conversational RAG context.
    Returns the top matching items.
    """
    query_embedding = await embed_text(query)

    query_str = """
        SELECT id, title, summary, source_type, source_url, tags, created_at,
               1 - (embedding <=> %s::vector) AS similarity
        FROM items
        WHERE user_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    async with db.cursor() as cur:
        await cur.execute(query_str, (query_embedding, user_id, query_embedding, limit))
        rows = await cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "source_type": r[3],
                "source_url": r[4],
                "tags": r[5] if r[5] is not None else [],
                "created_at": r[6],
                "similarity": float(r[7]),
            })

    return results


_CATEGORY_EMBEDDINGS = None

CATEGORY_TEXTS = {
    "Tech & Systems": "software development development programming development engineering python code database web development neural network systems",
    "Philosophy & Reflection": "philosophy reflection mind consciousness morality exist self introspection reflection",
    "Business & Strategy": "business product marketing finance startup growth client strategy entrepreneurship metric",
    "Art & Design": "art design creative drawing music aesthetics layout typography painting style",
    "Science & Nature": "science space nature physics astronomy ecology biology chemistry star planet environment"
}

async def get_category_embeddings() -> Dict[str, List[float]]:
    global _CATEGORY_EMBEDDINGS
    if _CATEGORY_EMBEDDINGS is None:
        _CATEGORY_EMBEDDINGS = {}
        for cat, text in CATEGORY_TEXTS.items():
            _CATEGORY_EMBEDDINGS[cat] = await embed_text(text)
    return _CATEGORY_EMBEDDINGS

async def determine_category(embedding: List[float]) -> str:
    if not embedding:
        return "General & Other"
    
    import numpy as np
    cat_embs = await get_category_embeddings()
    emb_np = np.array(embedding)
    
    best_cat = "General & Other"
    best_sim = -1.0
    
    for cat, cat_emb in cat_embs.items():
        cat_np = np.array(cat_emb)
        norm_emb = np.linalg.norm(emb_np)
        norm_cat = np.linalg.norm(cat_np)
        if norm_emb > 0 and norm_cat > 0:
            sim = np.dot(emb_np, cat_np) / (norm_emb * norm_cat)
            if sim > best_sim:
                best_sim = sim
                best_cat = cat
                
    if best_sim < 0.2:
        return "General & Other"
        
    return best_cat


