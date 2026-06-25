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
    """
    if settings.ENV == "test":
        # Return a normalized mock 384-dim vector for testing/local development
        val = 1.0 / (384 ** 0.5)
        return [val] * 384

    # 1. Try Modal if a real API token is configured
    if settings.MODAL_API_TOKEN and not settings.MODAL_API_TOKEN.startswith("ak-mock"):
        try:
            # Call the Modal MiniLM endpoint
            url = "https://pri27--minilm-embed.modal.run/embed"
            headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"text": text}, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) == 384:
                        return data
                else:
                    logger.warning("Modal embedding returned status code %d", response.status_code)
        except Exception as e:
            logger.error("Failed to generate embedding via Modal: %s", e)

    # 2. Try Local SentenceTransformer (if installed in the environment)
    try:
        from sentence_transformers import SentenceTransformer
        global _local_model
        if _local_model is None:
            logger.info("Initializing local SentenceTransformer('all-MiniLM-L6-v2')...")
            _local_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Run local CPU inference in executor so it doesn't block the main event loop
        import asyncio
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, lambda: _local_model.encode(text).tolist())
        if isinstance(embedding, list) and len(embedding) == 384:
            return embedding
    except ImportError:
        # Not installed in current environment, ignore and proceed to Gemini fallback
        pass
    except Exception as e:
        logger.error("Failed to generate local embedding: %s", e)

    # 3. Try Hugging Face Serverless Inference API if HF_TOKEN is configured
    if settings.HF_TOKEN and not settings.HF_TOKEN.startswith("mock") and settings.HF_TOKEN != "":
        try:
            url = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
            headers = {"Authorization": f"Bearer {settings.HF_TOKEN}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"inputs": text}, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        if len(data) == 384:
                            return data
                        elif len(data) > 0 and isinstance(data[0], list) and len(data[0]) == 384:
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
                        return embedding
                else:
                    logger.warning("Gemini embedding returned status code %d: %s", response.status_code, response.text)
        except Exception as e:
            logger.error("Failed to generate embedding via Gemini fallback: %s", e)

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

    vector_results = []
    text_results = []

    async with db.cursor() as cur:
        # Step 2a: Direct items vector search (HNSW cosine distance)
        vector_query = """
            SELECT id, title, summary, source_type, source_url, tags, created_at
            FROM items
            WHERE user_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT 20;
        """
        await cur.execute(vector_query, (user_id, query_embedding))
        rows = await cur.fetchall()
        direct_vector_results = []
        for r in rows:
            direct_vector_results.append({
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "source_type": r[3],
                "source_url": r[4],
                "tags": r[5] if r[5] is not None else [],
                "created_at": r[6],
            })

        # Step 2b: Chunks vector search (HNSW cosine distance)
        chunks_query = """
            SELECT item_id 
            FROM item_chunks 
            WHERE user_id = %s 
            ORDER BY embedding <=> %s::vector 
            LIMIT 50;
        """
        await cur.execute(chunks_query, (user_id, query_embedding))
        chunk_rows = await cur.fetchall()
        
        # Deduplicate while preserving rank order of first appearance
        chunk_item_ids = []
        seen_chunks = set()
        for r in chunk_rows:
            if r[0] not in seen_chunks:
                chunk_item_ids.append(r[0])
                seen_chunks.add(r[0])
                if len(chunk_item_ids) >= 20:
                    break
        
        # If we have matches from chunks, fetch their parent item details
        chunk_vector_results = []
        if chunk_item_ids:
            details_query = """
                SELECT id, title, summary, source_type, source_url, tags, created_at
                FROM items
                WHERE user_id = %s AND id = ANY(%s);
            """
            await cur.execute(details_query, (user_id, chunk_item_ids))
            detail_rows = await cur.fetchall()
            details_map = {r[0]: {
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "source_type": r[3],
                "source_url": r[4],
                "tags": r[5] if r[5] is not None else [],
                "created_at": r[6],
            } for r in detail_rows}
            
            # Maintain the sorting rank returned by the chunks query
            for item_id in chunk_item_ids:
                if item_id in details_map:
                    chunk_vector_results.append(details_map[item_id])

        # Merge direct vector matches and chunk-level vector matches, deduplicating by item id
        vector_results = []
        seen_ids = set()
        for item in direct_vector_results:
            if item["id"] not in seen_ids:
                vector_results.append(item)
                seen_ids.add(item["id"])
        for item in chunk_vector_results:
            if item["id"] not in seen_ids:
                vector_results.append(item)
                seen_ids.add(item["id"])

        # Step 3: GIN trigram search on items summary
        text_query = """
            SELECT id, title, summary, source_type, source_url, tags, created_at
            FROM items
            WHERE user_id = %s AND summary %% %s
            ORDER BY similarity(summary, %s) DESC
            LIMIT 20;
        """
        await cur.execute(text_query, (user_id, query, query))
        rows = await cur.fetchall()
        for r in rows:
            text_results.append({
                "id": r[0],
                "title": r[1],
                "summary": r[2],
                "source_type": r[3],
                "source_url": r[4],
                "tags": r[5] if r[5] is not None else [],
                "created_at": r[6],
            })

    # Step 4: Reciprocal Rank Fusion (RRF)
    rrf_scores = {}

    # Add vector search ranks (includes both direct matches and chunk matches)
    for rank, item in enumerate(vector_results, start=1):
        item_id = item["id"]
        if item_id not in rrf_scores:
            rrf_scores[item_id] = (item, 0.0)
        item_data, score = rrf_scores[item_id]
        rrf_scores[item_id] = (item_data, score + 1.0 / (rank + 60))

    # Add text search ranks
    for rank, item in enumerate(text_results, start=1):
        item_id = item["id"]
        if item_id not in rrf_scores:
            rrf_scores[item_id] = (item, 0.0)
        item_data, score = rrf_scores[item_id]
        rrf_scores[item_id] = (item_data, score + 1.0 / (rank + 60))

    # Sort merged, deduplicated results by score in descending order
    sorted_results = sorted(rrf_scores.values(), key=lambda x: x[1], reverse=True)

    # Return top 5 results with their RRF scores
    top_5 = []
    for item, score in sorted_results[:5]:
        item_copy = dict(item)
        item_copy["score"] = score
        top_5.append(item_copy)

    return top_5
