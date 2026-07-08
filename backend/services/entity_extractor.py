import logging
import json
import re
import unicodedata
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from psycopg import AsyncConnection

from backend.config import settings
from backend.services.ai_cascade import AICascade
from backend.services.search_service import embed_text

logger = logging.getLogger(__name__)

VALID_ENTITY_TYPES = {"Person", "Organization", "Project", "Technology", "Concept", "Location"}

SYSTEM_PROMPT = """
You are an expert knowledge graph extractor. Your task is to analyze the input text and extract key entities and relationships to build a semantic network.

Return a JSON object containing two lists:
1. "entities": Each entity must have:
   - "name": Canonical name of the entity.
   - "type": MUST be one of: "Person", "Organization", "Project", "Technology", "Concept", "Location".
   - "description": A brief explanation of the entity based on the context.
2. "relationships": Each relationship must have:
   - "source_name": Name of the source entity.
   - "source_type": Type of the source entity.
   - "target_name": Name of the target entity.
   - "target_type": Type of the target entity.
   - "predicate": The directed action connecting source to target (in lowercase, e.g., "uses", "works_on", "part_of", "related_to").
   - "description": A brief explanation of why this link exists in the context.
   - "confidence": A float between 0.0 and 1.0 representing your confidence in the extraction.

Strict JSON format only. Do not include markdown code block wraps.
"""

def normalize_entity_name(name: str) -> str:
    """
    Deterministically normalizes entity names by lowecasing, unicode NFKD normalization,
    filtering out combining diacritic marks, collapsing whitespaces, and trimming 
    leading/trailing non-alphanumeric punctuation.
    """
    if not name:
        return ""
    # Strip common trademark, register, and copyright symbols first
    name = re.sub(r"[™®©]", "", name)
    # Unicode decomposition to isolate accent marks
    decomp = unicodedata.normalize("NFKD", name)
    # Filter out combining character markings
    no_accents = "".join(c for c in decomp if not unicodedata.combining(c))
    normalized = no_accents.lower()
    # Collapse double spaces
    normalized = " ".join(normalized.split())
    # Trim leading/trailing punctuation characters (retaining alphanumeric/space)
    normalized = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", normalized)
    return normalized.strip()

async def extract_and_resolve_entities(item_id: int, user_id: int, text: str, db: Any) -> None:
    """
    Runs background entity extraction and resolution pipeline.
    Idempotent, handles concurrent execution conflicts, and updates the item status.
    Supports receiving either AsyncConnection or AsyncConnectionPool.
    """
    # Identify if db is a pool (has connection method but not cursor) to support connection mocks
    if hasattr(db, "connection") and not hasattr(db, "cursor"):
        async_conn_ctx = db.connection()
    else:
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def dummy_ctx():
            yield db
        async_conn_ctx = dummy_ctx()

    async with async_conn_ctx as db_conn:
        if not text or not text.strip():
            logger.info("Empty text for item %d, skipping entity extraction.", item_id)
            async with db_conn.cursor() as cur:
                await cur.execute(
                    "UPDATE items SET extraction_status = 'completed' WHERE id = %s AND user_id = %s;",
                    (item_id, user_id)
                )
                await db_conn.commit()
            return

        # 1. Update extraction status to 'running'
        async with db_conn.cursor() as cur:
            await cur.execute(
                "UPDATE items SET extraction_status = 'running' WHERE id = %s AND user_id = %s;",
                (item_id, user_id)
            )
            await db_conn.commit()

        cascade = AICascade()
        try:
            # Limit processed content to prevent prompt context explosion
            sample_text = text[:4000]
            prompt = f"Analyze the following text:\n---\n{sample_text}\n---\n{SYSTEM_PROMPT}"
            
            raw_res = await cascade.call_llm(prompt, temperature=0.1)
            if not raw_res:
                raise ValueError("AICascade call returned empty text.")

            # Use robust balanced JSON parsing from BaseValidator to handle leading/trailing conversational text
            from backend.services.ai_cascade.validators.base import BaseValidator
            class EntityExtractorValidator(BaseValidator):
                def validate(self, output: Dict[str, Any]) -> bool:
                    return True

            data = EntityExtractorValidator().parse_json(raw_res)

            extracted_entities = data.get("entities") or []
            extracted_relationships = data.get("relationships") or []

            entity_name_to_id = {}

            # 2. Entity Resolution & Ingestion Loop
            for ent in extracted_entities:
                name = ent.get("name")
                ent_type = ent.get("type") or "Concept"
                desc = ent.get("description") or ""

                if ent_type not in VALID_ENTITY_TYPES:
                    ent_type = "Concept"

                normalized = normalize_entity_name(name)
                if not normalized:
                    continue

                entity_id = None

                # Path A: Exact Match Lookup (Case-insensitive via normalized_name + type)
                async with db_conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, description FROM entities 
                        WHERE user_id = %s AND normalized_name = %s AND type = %s
                        LIMIT 1;
                        """,
                        (user_id, normalized, ent_type)
                    )
                    row = await cur.fetchone()
                    if row:
                        entity_id = row[0]
                        existing_desc = row[1]
                        logger.info("Entity resolution exact match found: name=%s type=%s -> ID=%d", name, ent_type, entity_id)
                        # Only populate description if current is empty to prevent identity drift
                        if not existing_desc and desc:
                            await cur.execute(
                                "UPDATE entities SET description = %s WHERE id = %s;",
                                (desc, entity_id)
                            )
                            await db_conn.commit()

                # Path B: Semantic Vector Similarity Resolution
                if not entity_id:
                    # Deterministic embedding of stable properties (excludes mutable description)
                    embedding = await embed_text(f"name: {normalized} | type: {ent_type.lower()}")
                    
                    async with db_conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT id, name, description, 1 - (embedding <=> %s::vector) AS similarity
                            FROM entities
                            WHERE user_id = %s AND type = %s
                            ORDER BY embedding <=> %s::vector
                            LIMIT 3;
                            """,
                            (embedding, user_id, ent_type, embedding)
                        )
                        candidates = await cur.fetchall()

                    for cand_id, cand_name, cand_desc, similarity in candidates:
                        if similarity >= settings.ENTITY_RESOLUTION_THRESHOLD:
                            logger.info("Entity resolution pgvector candidate found: %s (similarity=%.2f)", cand_name, similarity)
                            # Call LLM to confirm if they resolve to the same canonical entity
                            confirm_prompt = (
                                f"Do these two names in the context of personal notes refer to the same entity?\n"
                                f"Name A: {name} (Type: {ent_type}, Description: {desc})\n"
                                f"Name B: {cand_name} (Type: {ent_type}, Description: {cand_desc})\n"
                                f"Reply with 'YES' or 'NO' only."
                             )
                            confirm_res = await cascade.call_llm(confirm_prompt, temperature=0.0)
                            if confirm_res and "yes" in confirm_res.lower():
                                entity_id = cand_id
                                logger.info("AI Cascade confirmed resolution: %s -> %s", name, cand_name)
                                # Sync description if empty
                                if not cand_desc and desc:
                                    async with db_conn.cursor() as cur:
                                        await cur.execute(
                                            "UPDATE entities SET description = %s WHERE id = %s;",
                                            (desc, entity_id)
                                        )
                                        await db_conn.commit()
                                break

                # Path C: Create New Entity (Deterministic ON CONFLICT DO UPDATE handles concurrent races)
                if not entity_id:
                    embedding = await embed_text(f"name: {normalized} | type: {ent_type.lower()}")
                    async with db_conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO entities (user_id, name, normalized_name, type, description, embedding)
                            VALUES (%s, %s, %s, %s, %s, %s::vector)
                            ON CONFLICT (user_id, normalized_name, type) DO UPDATE SET
                                description = COALESCE(entities.description, EXCLUDED.description)
                            RETURNING id;
                            """,
                            (user_id, name, normalized, ent_type, desc, embedding)
                        )
                        row = await cur.fetchone()
                        if row:
                            entity_id = row[0]
                        else:
                            # Fallback SELECT if RETURNING was empty due to concurrency DO UPDATE shortcut
                            await cur.execute(
                                "SELECT id FROM entities WHERE user_id = %s AND normalized_name = %s AND type = %s;",
                                (user_id, normalized, ent_type)
                            )
                            fallback_row = await cur.fetchone()
                            if fallback_row:
                                entity_id = fallback_row[0]
                        await db_conn.commit()

                if entity_id:
                    entity_name_to_id[normalized] = entity_id
                    
                    # Insert mentioning provenance link (idempotent unique constraint handles retries)
                    async with db_conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO entity_mentions (user_id, entity_id, item_id, excerpt)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id, entity_id, item_id) DO NOTHING;
                            """,
                            (user_id, entity_id, item_id, desc)
                        )
                        await db_conn.commit()

            # 3. Relationship Ingestion Loop
            for rel in extracted_relationships:
                src_name = normalize_entity_name(rel.get("source_name"))
                tgt_name = normalize_entity_name(rel.get("target_name"))
                predicate = rel.get("predicate")
                rel_desc = rel.get("description") or ""
                confidence = float(rel.get("confidence") or 1.0)
                
                # Constrain confidence between 0.0 and 1.0
                confidence = max(0.0, min(1.0, confidence))

                src_id = entity_name_to_id.get(src_name)
                tgt_id = entity_name_to_id.get(tgt_name)

                if src_id and tgt_id and predicate:
                    async with db_conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO relationships (user_id, source_type, source_id, target_type, target_id, predicate, description, confidence, item_id)
                            VALUES (%s, 'entity', %s, 'entity', %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, source_type, source_id, target_type, target_id, predicate) DO NOTHING;
                            """,
                            (user_id, src_id, tgt_id, predicate.strip().lower(), rel_desc, confidence, item_id)
                        )
                        await db_conn.commit()

            # 4. Success State Update
            async with db_conn.cursor() as cur:
                await cur.execute(
                    "UPDATE items SET extraction_status = 'completed', extractor_version = 1 WHERE id = %s AND user_id = %s;",
                    (item_id, user_id)
                )
                await db_conn.commit()

        except Exception as exc:
            logger.error("Entity extraction failed for item %d: %s", item_id, exc, exc_info=True)
            # Update extraction status to 'failed' to allow background cron retries
            try:
                async with db_conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE items SET extraction_status = 'failed' WHERE id = %s AND user_id = %s;",
                        (item_id, user_id)
                    )
                    await db_conn.commit()
            except Exception as update_err:
                logger.error("Failed to set failed extraction status: %s", update_err)
