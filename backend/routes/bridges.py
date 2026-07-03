"""
backend/routes/bridges.py
=========================
FastAPI router for Cognitive Bridges and Thought Compatibility.
Allows users to connect, compare minds, and generate Spotify-style Blends.
"""

import string
import random
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.middleware.twa_auth import get_current_user, UserContext
from backend.db.connection import get_db
import psycopg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bridges", tags=["bridges"])

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class BridgeListItem(BaseModel):
    id: int
    friend_id: int
    friend_name: str
    friend_mind_type: Optional[str] = None
    friend_initials: str
    compatibility_score: float
    created_at: str

from datetime import datetime, timezone

class ConnectionRequest(BaseModel):
    code: str

class InviteResponse(BaseModel):
    code: str

class ThoughtBrief(BaseModel):
    id: int
    title: str
    summary: str
    created_at: datetime
    category: Optional[str] = None

class SynapsePair(BaseModel):
    item_a: ThoughtBrief
    item_b: ThoughtBrief
    similarity: float
    placement_cycle: int = 0
    decay_stage: str = "STABLE"
    has_gold_seam: bool = False
    parent_id: Optional[str] = None

class BridgeDetailsResponse(BaseModel):
    id: int
    friend_name: str
    friend_mind_type: Optional[str]
    user_mind_type: Optional[str] = None
    friend_initials: str
    compatibility_score: float
    synapses: List[SynapsePair]
    unique_user: List[str]
    unique_friend: List[str]
    time_cadence_user: Dict[str, int]
    time_cadence_friend: Dict[str, int]
    synergy_narrative: str
    last_ceremony_at: Optional[datetime] = None
    created_at: datetime
    consecutive_inactive_cycles: int = 0
    consecutive_active_cycles_since_decay_start: int = 0
    decay_front_position: Optional[int] = None

# ── Synergy Profile Generator ──────────────────────────────────────────────────

async def generate_synergy_profile(type_1: Optional[str], type_2: Optional[str], synapses: list) -> str:
    if not type_1 or not type_2:
        return "Your minds share an interesting overlap in specific subjects. Keep saving thoughts to map your full synergy!"
        
    from backend.services.ai_cascade import AICascade
    
    ARCHETYPES_DESC = {
        "BLVN": "Warp Navigator (broad, creative, high novelty, hyper-linked)",
        "FLVN": "Quantum Catalyst (focused, analytical, high novelty, hyper-linked)",
        "BLSN": "Nebula Weaver (broad, creative, deep history, hyper-linked)",
        "FLSN": "Alchemy Core (focused, analytical, deep history, hyper-linked)",
        "BLVR": "Ingestion Matrix (broad, creative, high novelty, refined focus)",
        "FLVR": "Laser Synthesizer (focused, analytical, high novelty, refined focus)",
        "BLSR": "Codex Cartographer (broad, creative, deep history, refined focus)",
        "FLSR": "Monolith Architect (focused, analytical, deep history, refined focus)",
        "BIVN": "Void Collector (broad, creative, high novelty, independent nodes)",
        "FIVN": "Recon Scout (focused, analytical, high novelty, independent nodes)",
        "BISN": "Archival Explorer (broad, creative, deep history, independent nodes)",
        "FISN": "Deep Diver (focused, analytical, deep history, independent nodes)",
        "BIVR": "Cyclone Curator (broad, creative, high novelty, structured nodes)",
        "FIVR": "Sentinel Core (focused, analytical, high novelty, structured nodes)",
        "BISR": "Silent Librarian (broad, creative, deep history, structured nodes)",
        "FISR": "Singular Vault (focused, analytical, deep history, structured nodes)"
    }
    
    desc_1 = ARCHETYPES_DESC.get(type_1, type_1)
    desc_2 = ARCHETYPES_DESC.get(type_2, type_2)
    
    overlap_themes = [f"'{s['item_a']['title']}' vs '{s['item_b']['title']}'" for s in synapses[:3]]
    themes_str = ", ".join(overlap_themes)
    
    prompt = (
        f"You are a cognitive profiling engine.\n"
        f"Provide a brief, engaging, high-end synergy profile (3 sentences max) "
        f"analyzing the compatibility between two minds.\n\n"
        f"User A is a {desc_1}.\n"
        f"User B is a {desc_2}.\n"
        f"Their overlapping themes include: {themes_str}.\n\n"
        f"Write a premium, inspiring description of how their cognitive styles interact, "
        f"referencing their archetypes and themes. Be direct, conversational, and futuristic."
    )
    try:
        cascade = AICascade()
        res = await cascade.call_llm(prompt)
        if res and "Mock completion" not in res:
            return res
    except Exception:
        pass
        
    return f"As a {type_1} and {type_2}, you merge {type_1[:2]} exploration with {type_2[:2]} synthesis. Your closest synaptic link centers around {synapses[0]['item_a']['title'] if synapses else 'shared concepts'}."

def simulate_kintsugi_decay(bridge_created_at: datetime, synapses: list, now: datetime) -> tuple:
    """
    Simulates the Kintsugi decay/repair process chronologically.
    Returns:
      (synapses, consecutive_inactive_cycles, consecutive_active_cycles_since_decay_start, decay_front_position)
    """
    # 1. Extract dates safely with per-synapse fallback handling
    def get_synapse_date(syn):
        try:
            if isinstance(syn, dict):
                da = syn["item_a"]["created_at"]
                db = syn["item_b"]["created_at"]
            else:
                da = syn.item_a.created_at
                db = syn.item_b.created_at
            
            if isinstance(da, str):
                da = datetime.fromisoformat(da.replace("Z", "+00:00"))
            if isinstance(db, str):
                db = datetime.fromisoformat(db.replace("Z", "+00:00"))
                
            s_date = max(da, db)
            if s_date.tzinfo is None:
                s_date = s_date.replace(tzinfo=timezone.utc)
            return s_date
        except Exception:
            b_date = bridge_created_at
            if b_date.tzinfo is None:
                b_date = b_date.replace(tzinfo=timezone.utc)
            return b_date

    # Sort synapses chronologically (ascending)
    sorted_syns = sorted(synapses, key=get_synapse_date)

    if bridge_created_at.tzinfo is None:
        bridge_created_at = bridge_created_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 2. Compute cycle indices relative to bridge creation
    # Cycle length is exactly 7 days
    cycle_length = 604800.0
    duration = now - bridge_created_at
    total_seconds = duration.total_seconds()
    num_cycles = int(total_seconds // cycle_length) + 1
    if num_cycles < 1:
        num_cycles = 1

    # Enrich each synapse with original index and placement cycle
    enriched_syns = []
    for i, syn in enumerate(sorted_syns):
        s_date = get_synapse_date(syn)
        s_diff = s_date - bridge_created_at
        s_cycle = int(s_diff.total_seconds() // cycle_length)
        if s_cycle < 0:
            s_cycle = 0
        enriched_syns.append({
            "syn": syn,
            "placement_cycle": s_cycle,
            "decay_stage": "STABLE",
            "has_gold_seam": False,
            "original_index": i
        })

    # 3. Simulate cycle-by-cycle decay and repair
    consecutive_inactive_cycles = 0
    consecutive_active_cycles_since_decay_start = 0
    stages = ["STABLE", "WEAKENED", "SMALL_CRACK", "WIDE_CRACK", "BROKEN"]

    for k in range(num_cycles):
        is_current_cycle = (k == num_cycles - 1)
        syns_in_cycle = [es for es in enriched_syns if es["placement_cycle"] == k]
        
        if len(syns_in_cycle) > 0:
            consecutive_inactive_cycles = 0
            damaged_stones = [es for es in enriched_syns if es["placement_cycle"] <= k and es["decay_stage"] != "STABLE"]
            
            if damaged_stones:
                consecutive_active_cycles_since_decay_start += 1
                oldest_damaged = None
                for es in enriched_syns:
                    if es["placement_cycle"] <= k and es["decay_stage"] != "STABLE":
                        oldest_damaged = es
                        break
                
                if oldest_damaged:
                    curr_idx = stages.index(oldest_damaged["decay_stage"])
                    new_stage = stages[curr_idx - 1]
                    oldest_damaged["decay_stage"] = new_stage
            else:
                consecutive_active_cycles_since_decay_start = 0
                
        else:
            if not is_current_cycle:
                consecutive_inactive_cycles += 1
                consecutive_active_cycles_since_decay_start = 0
                
                decay_front = None
                for es in reversed(enriched_syns):
                    if es["placement_cycle"] <= k and es["decay_stage"] != "BROKEN":
                        decay_front = es
                        break
                
                if decay_front:
                    curr_idx = stages.index(decay_front["decay_stage"])
                    new_stage = stages[curr_idx + 1]
                    decay_front["decay_stage"] = new_stage
                    if new_stage in ("SMALL_CRACK", "WIDE_CRACK", "BROKEN"):
                        decay_front["has_gold_seam"] = True

    decay_front_position = None
    for es in reversed(enriched_syns):
        if es["decay_stage"] != "BROKEN":
            decay_front_position = es["original_index"]
            break

    result_syns = []
    for es in enriched_syns:
        syn = es["syn"]
        if isinstance(syn, dict):
            syn["placement_cycle"] = es["placement_cycle"]
            syn["decay_stage"] = es["decay_stage"]
            syn["has_gold_seam"] = es["has_gold_seam"]
            result_syns.append(syn)
        else:
            syn.placement_cycle = es["placement_cycle"]
            syn.decay_stage = es["decay_stage"]
            syn.has_gold_seam = es["has_gold_seam"]
            result_syns.append(syn)
            
    return result_syns, consecutive_inactive_cycles, consecutive_active_cycles_since_decay_start, decay_front_position

# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[BridgeListItem])
async def list_bridges(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """List all established bridges for the user."""
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT 
                b.id,
                b.user_id_1,
                b.user_id_2,
                b.compatibility_score,
                b.created_at,
                u1.first_name, u1.username, u1.mind_type,
                u2.first_name, u2.username, u2.mind_type
            FROM cognitive_bridges b
            JOIN users u1 ON b.user_id_1 = u1.id
            JOIN users u2 ON b.user_id_2 = u2.id
            WHERE b.user_id_1 = %s OR b.user_id_2 = %s
            ORDER BY b.created_at DESC;
            """,
            (user.id, user.id)
        )
        rows = await cur.fetchall()
        
        result = []
        for r in rows:
            bridge_id = r[0]
            uid1, uid2 = r[1], r[2]
            score = float(r[3])
            created_at_str = r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4])
            
            # Determine which user is the friend
            if uid1 == user.id:
                friend_id = uid2
                friend_name = r[8] or r[9] or f"User {uid2}"
                friend_mind_type = r[10]
            else:
                friend_id = uid1
                friend_name = r[5] or r[6] or f"User {uid1}"
                friend_mind_type = r[7]
                
            initials = friend_name[0].upper() if friend_name else '?'
            
            result.append(
                BridgeListItem(
                    id=bridge_id,
                    friend_id=friend_id,
                    friend_name=friend_name,
                    friend_mind_type=friend_mind_type,
                    friend_initials=initials,
                    compatibility_score=score,
                    created_at=created_at_str
                )
            )
        return result

@router.post("/invite", response_model=InviteResponse)
async def generate_invite(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Generate a single-use bridge connection code."""
    # Check milestone requirement
    async with db.cursor() as cur:
        await cur.execute("SELECT node_milestones FROM users WHERE id = %s;", (user.id,))
        row = await cur.fetchone()
        milestones = row[0] if row and row[0] else {"unlocked": []}
        # Fallback to direct count if milestones column is somehow empty
        await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user.id,))
        count_row = await cur.fetchone()
        item_count = count_row[0] if count_row else 0
        
        unlocked = milestones.get("unlocked", [])
        if "compatibility" not in unlocked and item_count < 50:
            raise HTTPException(
                status_code=403,
                detail="Milestone locked. You need to save 50 items to unlock Cognitive Bridges."
            )
            
    # Generate random unique code
    chars = string.ascii_uppercase + string.digits
    code = "MIND-" + "".join(random.choices(chars, k=4)) + "-" + "".join(random.choices(chars, k=4))
    
    async with db.cursor() as cur:
        await cur.execute(
            "INSERT INTO bridge_invites (inviter_id, code) VALUES (%s, %s);",
            (user.id, code)
        )
        await db.commit()
        
    return InviteResponse(code=code)

@router.post("/connect", response_model=Dict[str, Any])
async def connect_bridge(
    req: ConnectionRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Claim an invite code and establish a cognitive bridge connection."""
    # Check milestone requirement
    async with db.cursor() as cur:
        await cur.execute("SELECT node_milestones FROM users WHERE id = %s;", (user.id,))
        row = await cur.fetchone()
        milestones = row[0] if row and row[0] else {"unlocked": []}
        await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user.id,))
        count_row = await cur.fetchone()
        item_count = count_row[0] if count_row else 0
        
        unlocked = milestones.get("unlocked", [])
        if "compatibility" not in unlocked and item_count < 50:
            raise HTTPException(
                status_code=403,
                detail="Milestone locked. You need to save 50 items to unlock Cognitive Bridges."
            )

    code = req.code.strip()
    
    # 1. Fetch invite
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT inviter_id FROM bridge_invites WHERE code = %s;",
            (code,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired invite code.")
            
        inviter_id = row[0]
        if inviter_id == user.id:
            raise HTTPException(status_code=400, detail="You cannot connect with yourself.")
            
    # Determine canonical user order
    user_id_1 = min(user.id, inviter_id)
    user_id_2 = max(user.id, inviter_id)
    
    # 2. Check if already connected
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id FROM cognitive_bridges WHERE user_id_1 = %s AND user_id_2 = %s;",
            (user_id_1, user_id_2)
        )
        existing = await cur.fetchone()
        if existing:
            # Delete single-use invite code anyway
            await cur.execute("DELETE FROM bridge_invites WHERE code = %s;", (code,))
            await db.commit()
            return {"status": "already_connected", "bridge_id": existing[0]}
            
    # 3. Create Bridge
    async with db.cursor() as cur:
        # Calculate dynamic initial compatibility score
        await cur.execute("""
            SELECT AVG(similarity) FROM (
                SELECT (1.0 - (a.embedding <=> b.embedding)) AS similarity
                FROM items a
                CROSS JOIN items b
                WHERE a.user_id = %s AND b.user_id = %s 
                  AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
                  AND a.title NOT ILIKE 'Bookmark:%%'
                  AND b.title NOT ILIKE 'Bookmark:%%'
                  AND a.summary NOT ILIKE '%%Could not process%%'
                  AND b.summary NOT ILIKE '%%Could not process%%'
                ORDER BY a.embedding <=> b.embedding
                LIMIT 5
            ) as subquery;
        """, (user_id_1, user_id_2))
        avg_row = await cur.fetchone()
        avg_sim = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.4
        score = round(max(0.0, min(100.0, avg_sim * 100.0)), 1)
        
        await cur.execute(
            """
            INSERT INTO cognitive_bridges (user_id_1, user_id_2, compatibility_score)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (user_id_1, user_id_2, score)
        )
        new_row = await cur.fetchone()
        bridge_id = new_row[0]
        
        # Consume invite
        await cur.execute("DELETE FROM bridge_invites WHERE code = %s;", (code,))
        await db.commit()
        
    return {"status": "connected", "bridge_id": bridge_id}

@router.get("/{bridge_id}", response_model=BridgeDetailsResponse)
async def get_bridge_details(
    bridge_id: int,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve dynamic Spotify-style Blend compatibility details for a bridge."""
    async with db.cursor() as cur:
        # Fetch bridge details and check membership
        await cur.execute(
            """
            SELECT 
                b.id, b.user_id_1, b.user_id_2, b.compatibility_score,
                u1.first_name, u1.username, u1.mind_type,
                u2.first_name, u2.username, u2.mind_type,
                b.last_ceremony_at, b.created_at, b.last_ceremony_at_1, b.last_ceremony_at_2
            FROM cognitive_bridges b
            JOIN users u1 ON b.user_id_1 = u1.id
            JOIN users u2 ON b.user_id_2 = u2.id
            WHERE b.id = %s;
            """,
            (bridge_id,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bridge not found.")
            
        uid1, uid2 = row[1], row[2]
        created_at = row[11]
        if user.id not in (uid1, uid2):
            raise HTTPException(status_code=403, detail="Access denied.")
            
        if user.id == uid1:
            last_ceremony_at = row[12]
        else:
            last_ceremony_at = row[13]
            
        # Determine friend info
        if uid1 == user.id:
            friend_id = uid2
            friend_name = row[7] or row[8] or f"User {uid2}"
            friend_mind_type = row[9]
            user_mind_type = row[6]
        else:
            friend_id = uid1
            friend_name = row[4] or row[5] or f"User {uid1}"
            friend_mind_type = row[6]
            user_mind_type = row[9]
            
        initials = friend_name[0].upper() if friend_name else '?'
        
        # 1. Top Aligned Concepts (Synapses)
        # Fetch up to 1000 synapses to ensure complete chronological history for the simulation
        await cur.execute("""
            SELECT 
                a.id AS a_id, a.title AS a_title, a.summary AS a_summary, a.category AS a_category, a.embedding AS a_embedding,
                b.id AS b_id, b.title AS b_title, b.summary AS b_summary, b.category AS b_category, b.embedding AS b_embedding,
                (1.0 - (a.embedding <=> b.embedding)) AS similarity,
                a.created_at AS a_created_at, b.created_at AS b_created_at
            FROM items a
            CROSS JOIN items b
            WHERE a.user_id = %s AND b.user_id = %s 
              AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
              AND a.title NOT ILIKE 'Bookmark:%%'
              AND b.title NOT ILIKE 'Bookmark:%%'
              AND a.summary NOT ILIKE '%%Could not process%%'
              AND b.summary NOT ILIKE '%%Could not process%%'
            ORDER BY a.embedding <=> b.embedding
            LIMIT 1000;
        """, (user.id, friend_id))
        synapse_rows = await cur.fetchall()
        
        from backend.services.search_service import determine_category
        import numpy as np
        import json

        synapses = []
        total_sim = 0.0
        synapse_embeddings = []

        for sr in synapse_rows:
            sim = max(0.0, float(sr[10])) # Clamp to prevent negative match scores
            total_sim += sim

            a_emb_data = sr[4]
            b_emb_data = sr[9]

            # Parse embeddings
            def parse_emb(emb_val):
                if not emb_val:
                    return None
                if isinstance(emb_val, str):
                    try:
                        return json.loads(emb_val)
                    except Exception:
                        pass
                if isinstance(emb_val, list):
                    return [float(x) for x in emb_val]
                try:
                    return list(emb_val)
                except Exception:
                    return None

            a_emb = parse_emb(a_emb_data)
            b_emb = parse_emb(b_emb_data)

            # Determine category fallback if NULL in DB
            a_cat = sr[3] or await determine_category(a_emb)
            b_cat = sr[8] or await determine_category(b_emb)

            # Compute average embedding for this synapse for nearest-branch calculation
            a_arr = np.array(a_emb) if a_emb else None
            b_arr = np.array(b_emb) if b_emb else None
            if a_arr is not None and b_arr is not None:
                syn_emb = (a_arr + b_arr) / 2.0
            elif a_arr is not None:
                syn_emb = a_arr
            else:
                syn_emb = b_arr

            synapse_embeddings.append(syn_emb)

            synapses.append(
                SynapsePair(
                    item_a=ThoughtBrief(
                        id=sr[0],
                        title=sr[1] or "Untitled",
                        summary=sr[2] or "",
                        category=a_cat,
                        created_at=sr[11]
                    ),
                    item_b=ThoughtBrief(
                        id=sr[5],
                        title=sr[6] or "Untitled",
                        summary=sr[7] or "",
                        category=b_cat,
                        created_at=sr[12]
                    ),
                    similarity=round(sim, 3)
                )
            )

        # Compute parents to establish nearest-branch hierarchy
        valid_embs = [emb for emb in synapse_embeddings if emb is not None]
        core_centroid = np.mean(valid_embs[:4], axis=0) if len(valid_embs) >= 4 else (np.mean(valid_embs, axis=0) if len(valid_embs) > 0 else np.zeros(384))

        def cosine_sim(v1, v2):
            if v1 is None or v2 is None:
                return 0.0
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)
            if n1 > 0 and n2 > 0:
                return float(np.dot(v1, v2) / (n1 * n2))
            return 0.0

        for i in range(len(synapses)):
            if i < 4:
                # The first 4 synapses form the core/foundation itself
                synapses[i].parent_id = "core"
            else:
                emb_i = synapse_embeddings[i]
                sim_to_core = cosine_sim(emb_i, core_centroid)
                
                # Check similarity against previously placed branch synapses (j >= 4)
                branch_sims = [cosine_sim(emb_i, synapse_embeddings[j]) for j in range(4, i)]
                
                if branch_sims and max(branch_sims) > sim_to_core:
                    best_j = 4 + np.argmax(branch_sims)
                    synapses[i].parent_id = f"s-{best_j}"
                else:
                    synapses[i].parent_id = "core"
            
        # Recalculate dynamic overall score based on top 15 latest thoughts
        top_syns = synapses[:15]
        total_top_sim = sum(s.similarity for s in top_syns)
        avg_sim = (total_top_sim / len(top_syns)) if top_syns else 0.4
        score = round(max(0.0, min(100.0, avg_sim * 100.0)), 1)

        # Run Kintsugi decay simulation
        try:
            synapses_enriched, consec_inactive, consec_active, decay_front_pos = simulate_kintsugi_decay(
                created_at, synapses, datetime.now(timezone.utc)
            )
        except Exception as sim_err:
            logger.error("Kintsugi simulation failed: %s", sim_err)
            synapses_enriched = []
            for s in synapses:
                s.placement_cycle = 0
                s.decay_stage = "STABLE"
                s.has_gold_seam = False
                synapses_enriched.append(s)
            consec_inactive = 0
            consec_active = 0
            decay_front_pos = None
        
        # 2. Unique Horizons (Distinct specialized tags)
        await cur.execute("SELECT tags FROM items WHERE user_id = %s AND tags IS NOT NULL;", (user.id,))
        tags_user_rows = await cur.fetchall()
        await cur.execute("SELECT tags FROM items WHERE user_id = %s AND tags IS NOT NULL;", (friend_id,))
        tags_friend_rows = await cur.fetchall()
        
        tags_user_counts = {}
        for r in tags_user_rows:
            for t in r[0]:
                tags_user_counts[t] = tags_user_counts.get(t, 0) + 1
                
        tags_friend_counts = {}
        for r in tags_friend_rows:
            for t in r[0]:
                tags_friend_counts[t] = tags_friend_counts.get(t, 0) + 1
                
        unique_user = [t for t, c in sorted(tags_user_counts.items(), key=lambda x: -x[1]) if t not in tags_friend_counts][:5]
        unique_friend = [t for t, c in sorted(tags_friend_counts.items(), key=lambda x: -x[1]) if t not in tags_user_counts][:5]
        
        # 3. Resonance (Time Bucket Comparison)
        await cur.execute("""
            SELECT save_time_bucket, COUNT(*) 
            FROM items 
            WHERE user_id = %s AND save_time_bucket IS NOT NULL
            GROUP BY save_time_bucket;
        """, (user.id,))
        times_user_rows = await cur.fetchall()
        
        await cur.execute("""
            SELECT save_time_bucket, COUNT(*) 
            FROM items 
            WHERE user_id = %s AND save_time_bucket IS NOT NULL
            GROUP BY save_time_bucket;
        """, (friend_id,))
        times_friend_rows = await cur.fetchall()
        
        time_cadence_user = {r[0]: r[1] for r in times_user_rows}
        time_cadence_friend = {r[0]: r[1] for r in times_friend_rows}
        
        # 4. Synergy Narrative (LLM-based)
        # Prepare synapses details to pass to generator
        synapses_raw = []
        for sy in synapses[:15]:  # limit narrative context to top 15 to avoid token bloat
            synapses_raw.append({
                "item_a": {"title": sy.item_a.title},
                "item_b": {"title": sy.item_b.title}
            })
        narrative = await generate_synergy_profile(user_mind_type, friend_mind_type, synapses_raw)
        
        # Optional: Save updated score
        await cur.execute("UPDATE cognitive_bridges SET compatibility_score = %s WHERE id = %s;", (score, bridge_id))
        await db.commit()
        
        return BridgeDetailsResponse(
            id=bridge_id,
            friend_name=friend_name,
            friend_mind_type=friend_mind_type,
            user_mind_type=user_mind_type,
            friend_initials=initials,
            compatibility_score=score,
            synapses=synapses_enriched,
            unique_user=unique_user,
            unique_friend=unique_friend,
            time_cadence_user=time_cadence_user,
            time_cadence_friend=time_cadence_friend,
            synergy_narrative=narrative,
            last_ceremony_at=last_ceremony_at,
            created_at=created_at,
            consecutive_inactive_cycles=consec_inactive,
            consecutive_active_cycles_since_decay_start=consec_active,
            decay_front_position=decay_front_pos
        )

@router.post("/{bridge_id}/ceremony", response_model=Dict[str, str])
async def update_bridge_ceremony(
    bridge_id: int,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Update last_ceremony_at timestamp for a bridge."""
    async with db.cursor() as cur:
        await cur.execute("SELECT user_id_1, user_id_2 FROM cognitive_bridges WHERE id = %s;", (bridge_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bridge not found.")
            
        uid1, uid2 = row[0], row[1]
        if user.id not in (uid1, uid2):
            raise HTTPException(status_code=403, detail="Access denied.")
            
        if user.id == uid1:
            await cur.execute("UPDATE cognitive_bridges SET last_ceremony_at_1 = NOW(), last_ceremony_at = NOW() WHERE id = %s;", (bridge_id,))
        else:
            await cur.execute("UPDATE cognitive_bridges SET last_ceremony_at_2 = NOW(), last_ceremony_at = NOW() WHERE id = %s;", (bridge_id,))
        await db.commit()
        
    return {"status": "updated"}

@router.delete("/{bridge_id}", response_model=Dict[str, str])
async def delete_bridge(
    bridge_id: int,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Delete a bridge connection."""
    async with db.cursor() as cur:
        await cur.execute("SELECT user_id_1, user_id_2 FROM cognitive_bridges WHERE id = %s;", (bridge_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bridge not found.")
            
        uid1, uid2 = row[0], row[1]
        if user.id not in (uid1, uid2):
            raise HTTPException(status_code=403, detail="Access denied.")
            
        await cur.execute("DELETE FROM cognitive_bridges WHERE id = %s;", (bridge_id,))
        await db.commit()
        
    return {"status": "deleted"}
