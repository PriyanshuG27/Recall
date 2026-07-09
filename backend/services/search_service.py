import logging
import math
from datetime import datetime, timezone
import asyncio
import re
import json
from typing import List, Dict, Any, Optional, Tuple
import httpx
from psycopg import AsyncConnection

from backend.config import settings

logger = logging.getLogger(__name__)

def _build_metadata_filters(
    alias: str,
    source_types: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> tuple[List[str], List[Any]]:
    """
    Constructs clean, parameterized SQL filter conditions and their associated arguments.
    Uses the table alias explicitly to ensure identical predicates across CTEs.
    """
    conditions = []
    params = []
    if source_types:
        conditions.append(f"{alias}.source_type = ANY(%s)")
        params.append(source_types)
    if tags:
        conditions.append(f"{alias}.tags && %s")
        params.append(tags)
    if start_date:
        conditions.append(f"{alias}.created_at >= %s")
        params.append(start_date.astimezone(timezone.utc))
    if end_date:
        conditions.append(f"{alias}.created_at <= %s")
        params.append(end_date.astimezone(timezone.utc))
    return conditions, params

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

    if getattr(settings, "EMBEDDING_PROVIDER", "local") == "remote":
        from backend.services.remote_ai_client import generate_remote_embedding
        return await generate_remote_embedding(text)

    # 1. Try Modal if a real API token is configured
    if settings.MODAL_API_TOKEN and not settings.MODAL_API_TOKEN.startswith("ak-mock"):
        try:
            logger.info("Attempting embedding generation via Modal...")
            # Call the Modal MiniLM endpoint
            url = settings.MODAL_EMBED_URL or "https://modal.run/embed"
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
            logger.info("Initializing local SentenceTransformer('BAAI/bge-small-en-v1.5')...")
            _local_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        
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
            url = "https://api-inference.huggingface.co/pipeline/feature-extraction/BAAI/bge-small-en-v1.5"
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
def should_bypass_rewrite(query: str) -> bool:
    """
    Heuristically checks if a query should bypass the LLM rewriter to save latency & cost.
    Bypasses if:
    - Word count <= QUERY_REWRITE_MAX_WORDS
    - Query is quoted (e.g. '"fastapi guide"')
    - Query is a raw tag or hashtag format (e.g. '#work', 'work')
    - Query matches a simple alphanumeric exact pattern without spaces
    """
    q_trimmed = query.strip()
    if not q_trimmed:
        return True
        
    # Check if quoted
    if (q_trimmed.startswith('"') and q_trimmed.endswith('"')) or \
       (q_trimmed.startswith("'") and q_trimmed.endswith("'")):
        return True
        
    # Check word count
    words = q_trimmed.split()
    if len(words) <= settings.QUERY_REWRITE_MAX_WORDS:
        return True
        
    # Check exact alphanumeric word tag (no spaces)
    if len(words) == 1:
        return True
        
    return False

async def rewrite_search_query(query: str) -> Tuple[str, List[str]]:
    """
    Standardize and expand search queries before execution using the AICascade.
    Strictly instructs the model to preserve intent, normalize wording, and generate synonyms.
    Restricts synonyms to 2-3 single keywords (no phrases/explanations).
    Enforces a strict timeout task with cancellation to prevent latency penalty.
    """
    # 1. Check heuristic bypass
    if should_bypass_rewrite(query):
        logger.info("Bypassed search query rewrite heuristically.")
        return query, []
        
    if not settings.ENABLE_QUERY_REWRITING:
        return query, []

    from backend.services.ai_cascade.facade import AICascade
    cascade = AICascade()

    prompt = (
        "You are an expert search query optimization agent.\n"
        "Your task is to rewrite the user's raw search query to improve retrieval quality in a vector database and full-text keyword search.\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Rewrite the query for retrieval. DO NOT answer the query. DO NOT infer missing facts.\n"
        "2. Preserve the query's original intent exactly. DO NOT narrow the scope. DO NOT broaden the scope.\n"
        "3. Only normalize wording and generate close synonyms/alternate terms.\n"
        "4. Generate a list of 2-3 synonyms. Synonyms must be single keywords, technologies, or concepts. STRICTLY forbid multi-word phrases, sentences, or explanations.\n"
        "5. Do not introduce named entities that were not present in the user query unless they are direct lexical variants (e.g. 'postgres' -> 'postgresql').\n"
        "6. Do not introduce named entities that were not present unless they are direct lexical variants.\n\n"
        "Input query: {query}\n\n"
        "Output your response strictly as a JSON object matching this schema:\n"
        "{\n"
        "  \"rewritten_query\": \"A search query optimized for embedding representation\",\n"
        "  \"synonyms\": [\"synonym1\", \"synonym2\"]\n"
        "}"
    ).replace("{query}", query)

    import time
    duration_ms = 0.0
    start_time = time.perf_counter()
    rewrite_task = None
    try:
        # Wrap LLM call in an asyncio task to allow cancellation on timeout
        async def call_cascade():
            return await cascade.call_llm(prompt, temperature=0.0)
            
        rewrite_task = asyncio.create_task(call_cascade())
        
        # Enforce strict timeout
        raw_res = await asyncio.wait_for(rewrite_task, timeout=settings.QUERY_REWRITE_TIMEOUT_SECONDS)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        if not raw_res:
            raise ValueError("Empty response from model.")

        # Use robust balanced JSON parsing from BaseValidator
        from backend.services.ai_cascade.validators.base import BaseValidator
        class QueryRewriterValidator(BaseValidator):
            def validate(self, output: Dict[str, Any]) -> bool:
                return True

        data = QueryRewriterValidator().parse_json(raw_res)

        rewritten = data.get("rewritten_query", "").strip() or query
        synonyms_raw = data.get("synonyms") or []
        
        # Bounding synonyms logic:
        # - Max 3
        # - Single keywords only (no spaces)
        # - Lowercase & strip
        # - Remove overlapping words present in the rewritten query or original query
        # - Remove duplicates & empty values
        synonyms = []
        seen_words = set()
        for s_str in (rewritten, query):
            for w in s_str.lower().split():
                w_clean = re.sub(r"[^\w]+", "", w)
                if w_clean:
                    seen_words.add(w_clean)

        for syn in synonyms_raw:
            if not isinstance(syn, str):
                continue
            syn_clean = syn.strip().lower()
            syn_clean = re.sub(r"[^\w]+", "", syn_clean)
            if not syn_clean or " " in syn_clean:
                continue
            if syn_clean not in seen_words:
                seen_words.add(syn_clean)
                synonyms.append(syn_clean)
                
        synonyms = synonyms[:3]
        
        logger.info(
            "query_rewrite_success duration_ms=%.1f provider=default",
            duration_ms
        )
        return rewritten, synonyms

    except asyncio.TimeoutError:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "query_rewrite_timeout duration_ms=%.1f provider=default",
            duration_ms
        )
        if rewrite_task and not rewrite_task.done():
            rewrite_task.cancel()
        return query, []
    except json.JSONDecodeError as jde:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            "query_rewrite_malformed_json duration_ms=%.1f provider=default error=%s",
            duration_ms, jde
        )
        return query, []
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            "query_rewrite_provider_error duration_ms=%.1f provider=default error=%s",
            duration_ms, exc
        )
        return query, []

import time

async def hybrid_search(
    query: str,
    user_id: int,
    db: AsyncConnection,
    source_types: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bypass_rewrite: bool = False
) -> List[Dict[str, Any]]:
    """
    Perform a hybrid search using pgvector (HNSW cosine distance) on both items and item_chunks,
    and pg_trgm (GIN trigram similarity) on items.
    Enforces precise database-level metadata filtering dynamically.
    Combines results using Reciprocal Rank Fusion (RRF) and runs a SOTA reranker step.
    """
    # Step 1: Optional Query Rewriting & Generation of search term parameters
    if bypass_rewrite:
        rewritten = query
        synonyms = []
    else:
        rewritten, synonyms = await rewrite_search_query(query)

    t_emb_start = time.perf_counter()
    query_embedding = await embed_text(rewritten)
    t_emb = (time.perf_counter() - t_emb_start) * 1000

    is_reranking_active = settings.ENABLE_RERANKING and settings.RERANKER_MODEL != "benchmark_pending"
    db_limit = settings.RERANK_CANDIDATES if is_reranking_active else settings.RERANK_TOP_N

    # Build dynamic filter constraints using explicit table alias "i"
    conditions, filter_params = _build_metadata_filters("i", source_types, tags, start_date, end_date)
    filter_clause = (" AND " + " AND ".join(conditions)) if conditions else ""

    # Build tsquery expression for Full Text Search (FTS)
    # Default configuration is 'english'; stemming/tokenization is language-specific.
    tsquery_parts = ["websearch_to_tsquery('english', %s)"]
    tsquery_params = [rewritten]
    for syn in synonyms:
        tsquery_parts.append("to_tsquery('english', %s)")
        tsquery_params.append(syn)
    
    tsquery_expression = " || ".join(tsquery_parts)
    if len(tsquery_parts) > 1:
        tsquery_expression = f"({tsquery_expression})"

    consolidated_query = f"""
        WITH latest_chunks AS (
            SELECT item_id, MAX(chunk_version) AS chunk_version
            FROM item_chunks
            GROUP BY item_id
        ),
        direct_vector AS (
            SELECT i.id, ROW_NUMBER() OVER (ORDER BY i.embedding <=> %s::vector) as rank
            FROM items i
            WHERE i.user_id = %s AND (i.embedding <=> %s::vector) < 0.8 {filter_clause}
            ORDER BY i.embedding <=> %s::vector
            LIMIT %s
        ),
        chunk_vector AS (
            SELECT item_id AS id, ROW_NUMBER() OVER (ORDER BY min_row_num) as rank
            FROM (
                SELECT sub.item_id, MIN(row_num) as min_row_num
                FROM (
                    SELECT c.item_id, ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s::vector) as row_num
                    FROM item_chunks c
                    JOIN items i ON c.item_id = i.id AND c.user_id = i.user_id
                    JOIN latest_chunks lc ON c.item_id = lc.item_id AND c.chunk_version = lc.chunk_version
                    WHERE c.user_id = %s AND (c.embedding <=> %s::vector) < 0.8 {filter_clause}
                    LIMIT 50
                ) sub
                GROUP BY item_id
            ) sub2
            ORDER BY min_row_num
            LIMIT %s
        ),
        combined_vector_ids AS (
            SELECT id, MIN(val_rank) AS final_rank
            FROM (
                SELECT id, rank AS val_rank FROM direct_vector
                UNION ALL
                SELECT id, rank + %s AS val_rank FROM chunk_vector
            ) u
            GROUP BY id
        ),
        ranked_vector AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY final_rank) as rank
            FROM combined_vector_ids
        ),
        fts_search AS (
            SELECT i.id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('english', COALESCE(i.summary, '')), query_ts.query_ts) DESC) as rank
            FROM items i, (SELECT {tsquery_expression}) AS query_ts(query_ts)
            WHERE i.user_id = %s AND to_tsvector('english', COALESCE(i.summary, '')) @@ query_ts.query_ts {filter_clause}
            ORDER BY ts_rank_cd(to_tsvector('english', COALESCE(i.summary, '')), query_ts.query_ts) DESC
            LIMIT %s
        ),
        fts_count AS (
            SELECT COUNT(*) AS cnt FROM fts_search
        ),
        trigram_search AS (
            SELECT i.id, ROW_NUMBER() OVER (ORDER BY similarity(summary, %s) DESC) as rank
            FROM items i, fts_count fc
            WHERE i.user_id = %s AND fc.cnt = 0 AND i.summary %% %s AND similarity(summary, %s) >= %s {filter_clause}
            ORDER BY similarity(summary, %s) DESC
            LIMIT %s
        ),
        text_search AS (
            SELECT id, rank FROM fts_search
            UNION ALL
            SELECT id, rank FROM trigram_search
        ),
        rrf_scores AS (
            SELECT 
                COALESCE(v.id, t.id) as id,
                COALESCE(%s::float / (v.rank + %s::int), 0.0) + COALESCE(%s::float / (t.rank + %s::int), 0.0) as rrf_score
            FROM ranked_vector v
            FULL OUTER JOIN text_search t ON v.id = t.id
        ),
        best_chunk AS (
            SELECT DISTINCT ON (c.item_id) c.item_id, c.chunk_text, c.chunk_index
            FROM item_chunks c
            JOIN latest_chunks lc ON c.item_id = lc.item_id AND c.chunk_version = lc.chunk_version
            WHERE c.user_id = %s AND (c.embedding <=> %s::vector) < 0.8
            ORDER BY c.item_id, c.embedding <=> %s::vector
        )
        SELECT 
            i.id, i.title, i.summary, i.source_type, i.source_url, i.tags, i.created_at,
            r.rrf_score, i.raw_text, bc.chunk_text, bc.chunk_index
        FROM rrf_scores r
        JOIN items i ON r.id = i.id
        LEFT JOIN best_chunk bc ON i.id = bc.item_id
        WHERE i.user_id = %s
        ORDER BY r.rrf_score DESC
        LIMIT %s;
    """

    # Assemble dynamic parameters exactly matching query placeholders
    query_params = []
    
    # 1. direct_vector
    query_params.extend([query_embedding, user_id, query_embedding])
    query_params.extend(filter_params)
    query_params.extend([query_embedding, db_limit])
    
    # 2. chunk_vector
    query_params.extend([query_embedding, user_id, query_embedding])
    query_params.extend(filter_params)
    query_params.extend([db_limit])
    
    # 3. combined_vector_ids (rank + db_limit)
    query_params.append(db_limit)
    
    # 4. fts_search
    query_params.extend(tsquery_params)
    query_params.append(user_id)
    query_params.extend(filter_params)
    query_params.append(db_limit)
    
    # 5. trigram_search (falls back if FTS count is 0)
    query_params.extend([query, user_id, query, query, settings.TRIGRAM_MIN_SIMILARITY])
    query_params.extend(filter_params)
    query_params.extend([query, db_limit])
    
    # 6. rrf_scores
    query_params.extend([settings.RRF_VECTOR_WEIGHT, settings.RRF_K, settings.RRF_TEXT_WEIGHT, settings.RRF_K])

    # 7. best_chunk
    query_params.extend([user_id, query_embedding, query_embedding])
    
    # 8. final SELECT
    query_params.extend([user_id, db_limit])

    t_db_start = time.perf_counter()
    async with db.cursor() as cur:
        await cur.execute(consolidated_query, tuple(query_params))
        rows = await cur.fetchall()
        t_db = (time.perf_counter() - t_db_start) * 1000

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
                "raw_text": r[8] if len(r) > 8 else None,
                "matched_chunk_text": r[9] if len(r) > 9 else None,
                "chunk_index": r[10] if len(r) > 10 else None,
            })

    # If the database returns 0 candidate matches, skip reranking and return [] immediately
    if not results:
        t_rerank = 0.0
        logger.info(f"[PROFILER] Embedding: {t_emb:.1f} ms | DB Vector/Text Search: {t_db:.1f} ms | Reranker (Bypassed): {t_rerank:.1f} ms")
        return []

    # Step 2: Rerank Child Chunks
    t_rerank_start = time.perf_counter()
    if is_reranking_active:
        from backend.services.reranker import reranker_service
        results = await reranker_service.rerank(query, results)
    t_rerank = (time.perf_counter() - t_rerank_start) * 1000
    
    logger.info(f"[PROFILER] Embedding: {t_emb:.1f} ms | DB Vector/Text Search: {t_db:.1f} ms | Reranker: {t_rerank:.1f} ms")
    
    # Select winning top results
    winners = results[:settings.RERANK_TOP_N]

    # Step 3: Dynamic Context Expansion
    start_time = time.perf_counter()
    from collections import defaultdict
    
    # Group matched chunks by item_id to deduplicate
    item_to_indices = defaultdict(list)
    for w in winners:
        item_id = w["id"]
        idx = w.get("chunk_index")
        if idx is not None:
            item_to_indices[item_id].append(idx)
            
    # Plan sibling index queries (fetch from min(matched_idx) - 2 to max(matched_idx) + 2)
    sql_coords = []
    for item_id, indices in item_to_indices.items():
        unique_indices = set()
        for idx in indices:
            for sibling_idx in range(max(0, idx - 2), idx + 3):
                unique_indices.add(sibling_idx)
        for sibling_idx in sorted(unique_indices):
            sql_coords.append((item_id, sibling_idx))
            
    # Single trip database join for all sibling chunks
    sibling_chunks = defaultdict(list)
    if sql_coords:
        values_placeholders = ", ".join(f"(%s::int, %s::int)" for _ in sql_coords)
        flat_params = []
        for item_id, s_idx in sql_coords:
            flat_params.extend([item_id, s_idx])
            
        sibling_query = f"""
            WITH target_chunks(item_id, chunk_index) AS (
                VALUES {values_placeholders}
            ),
            latest_versions AS (
                SELECT item_id, MAX(chunk_version) AS max_v
                FROM item_chunks
                WHERE item_id IN ({", ".join(str(w["id"]) for w in winners)})
                GROUP BY item_id
            )
            SELECT c.item_id, c.chunk_index, c.chunk_text
            FROM item_chunks c
            JOIN target_chunks t ON c.item_id = t.item_id AND c.chunk_index = t.chunk_index
            JOIN latest_versions lv ON c.item_id = lv.item_id AND c.chunk_version = lv.max_v
            ORDER BY c.item_id, c.chunk_index;
        """
        async with db.cursor() as cur:
            await cur.execute(sibling_query, flat_params)
            sibling_rows = await cur.fetchall()
            for s_row in sibling_rows:
                sibling_chunks[s_row[0]].append((s_row[1], s_row[2]))

    # Perform adaptive outward context expansion on sentences using spaCy
    from backend.services.nlp import get_spacy_sentencizer
    nlp = get_spacy_sentencizer()
    
    for w in winners:
        item_id = w["id"]
        matched_idx = w.get("chunk_index")
        matched_text = w.get("matched_chunk_text") or ""
        
        siblings = sibling_chunks[item_id]
        if siblings and matched_idx is not None:
            # Sort by chunk_index and join to get contiguous text block
            sorted_s = sorted(siblings, key=lambda x: x[0])
            full_text = " ".join(s[1] for s in sorted_s)
            
            # Segment into sentences
            sentences = [sent.text.strip() for sent in nlp(full_text).sents if sent.text.strip()]
            
            # Find the starting sentence index range that matches the child chunk
            matched_indices = []
            if matched_text:
                for i, sent in enumerate(sentences):
                    if sent in matched_text or matched_text in sent:
                        matched_indices.append(i)
                        
            if not matched_indices:
                matched_indices = [len(sentences) // 2] if sentences else [0]
                
            selected_indices = set(matched_indices)
            left = min(matched_indices) - 1
            right = max(matched_indices) + 1
            
            current_words = sum(len(sentences[i].split()) for i in selected_indices if i < len(sentences))
            
            # Outward sentence expansion
            while current_words < settings.PARENT_TARGET_WORDS:
                expanded = False
                if left >= 0:
                    word_count = len(sentences[left].split())
                    if current_words + word_count <= settings.MAX_EXPANDED_WORDS:
                        selected_indices.add(left)
                        current_words += word_count
                        left -= 1
                        expanded = True
                if right < len(sentences) and current_words < settings.PARENT_TARGET_WORDS:
                    word_count = len(sentences[right].split())
                    if current_words + word_count <= settings.MAX_EXPANDED_WORDS:
                        selected_indices.add(right)
                        current_words += word_count
                        right += 1
                        expanded = True
                if not expanded:
                    break
                    
            expanded_sentences = [sentences[i] for i in sorted(selected_indices) if i < len(sentences)]
            w["expanded_context"] = " ".join(expanded_sentences)
        else:
            w["expanded_context"] = matched_text

        # Reserved Extension Point: Context Compression / Token Filtering
        # w["expanded_context"] = await compress_context(w["expanded_context"])

    # Measure and log operational performance metrics at DEBUG level
    end_time = time.perf_counter()
    latency = end_time - start_time
    merge_rate = (len(winners) - len(item_to_indices)) / len(winners) if winners else 0.0
    avg_words = sum(len(w.get("expanded_context", "").split()) for w in winners) / len(winners) if winners else 0.0
    
    logger.info(
        "Dynamic Context Expansion Metrics: Avg Word Count: %.2f | Latency: %.2f ms | Merge Rate: %.2f%%",
        avg_words, latency * 1000, merge_rate * 100
    )

    # Strip raw_text and temporary chunk_index from results, while keeping matched_chunk_text and expanded_context
    for r in winners:
        r.pop("raw_text", None)
        r.pop("chunk_index", None)

    return winners


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


