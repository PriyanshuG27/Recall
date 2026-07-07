import logging
import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.middleware.twa_auth import verify_jwt
from backend.config import settings
from backend.services.redis_client import redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# In-memory registry for backward compatibility / single-instance fallback
active_connections: dict[int, WebSocket] = {}

# Local instance-specific registry: {connection_id: WebSocket}
active_local_websockets: dict[str, WebSocket] = {}

async def broadcast(user_id: int, event: dict) -> None:
    """Broadcast an event to all of the user's active connection queues in Redis (and fallback registry)."""
    # Fallback/mock direct local push
    local_ws = active_connections.get(user_id)
    if local_ws:
        try:
            await local_ws.send_json(event)
        except Exception:
            if user_id in active_connections and active_connections[user_id] == local_ws:
                del active_connections[user_id]

    try:
        # 1. Fetch connection IDs registered for this user
        connection_ids = await redis.smembers(f"ws:connections:user:{user_id}")
        if not connection_ids:
            return
        
        # 2. Check heartbeat keys to verify connection liveness in a single pipeline
        pipeline_exists_cmds = [["EXISTS", f"ws:heartbeat:{user_id}:{conn_id}"] for conn_id in connection_ids]
        exists_results = await redis.pipeline(pipeline_exists_cmds)
        
        pipeline_cmds = []
        for idx, conn_id in enumerate(connection_ids):
            res_obj = exists_results[idx]
            exists = False
            if isinstance(res_obj, dict):
                exists = bool(res_obj.get("result", 0))
            elif isinstance(res_obj, (int, str)):
                exists = bool(int(res_obj))
            
            if exists:
                list_key = f"ws:user:{user_id}:{conn_id}"
                pipeline_cmds.append(["RPUSH", list_key, json.dumps(event)])
                pipeline_cmds.append(["EXPIRE", list_key, "3600"])  # 1 hour safety TTL
            else:
                # Prune dead connection registry
                pipeline_cmds.append(["SREM", f"ws:connections:user:{user_id}", conn_id])
        
        if pipeline_cmds:
            await redis.pipeline(pipeline_cmds)
            
    except Exception as broadcast_err:
        logger.error("Failed to broadcast multi-server WebSocket event for user %d: %s", user_id, broadcast_err)

from typing import Optional

@router.websocket("/ws")
@router.websocket("/ws/{token}")
@router.websocket("/api/ws")
@router.websocket("/api/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    # Try getting token from cookies if not in path
    jwt_token = token
    if not jwt_token:
        jwt_token = websocket.cookies.get("recall_session") or websocket.cookies.get("jwt")
    
    if not jwt_token:
        await websocket.close(code=4001)
        return

    # Validate the JWT
    try:
        payload = verify_jwt(jwt_token, settings.JWT_SECRET)
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=4001)
            return
        user_id = int(user_id_str)
    except Exception:
        await websocket.close(code=4001)
        return

    # Accept the connection
    await websocket.accept()

    # Generate a unique connection ID for horizontal routing
    connection_id = uuid.uuid4().hex

    # Register the connection in Redis
    try:
        await redis.sadd(f"ws:connections:user:{user_id}", connection_id)
        await redis.setex(f"ws:heartbeat:{user_id}:{connection_id}", 60, "1")
        active_local_websockets[connection_id] = websocket
        active_connections[user_id] = websocket
    except Exception as reg_err:
        logger.error("Failed to register WebSocket in Redis: %s", reg_err)
        await websocket.close(code=4000)
        return

    # Immediately send the connected event
    try:
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id
        })
    except Exception:
        # Cleanup
        try:
            await redis.srem(f"ws:connections:user:{user_id}", connection_id)
            await redis.delete(f"ws:heartbeat:{user_id}:{connection_id}")
        except Exception:
            pass
        active_local_websockets.pop(connection_id, None)
        if user_id in active_connections and active_connections[user_id] == websocket:
            del active_connections[user_id]
        return

    # Ping/pong maintenance loop
    pong_received = asyncio.Event()

    async def ping_task():
        try:
            while True:
                await asyncio.sleep(30.0)
                # Refresh heartbeat key in Redis
                await redis.setex(f"ws:heartbeat:{user_id}:{connection_id}", 60, "1")
                pong_received.clear()
                await websocket.send_json({"type": "ping"})
                try:
                    await asyncio.wait_for(pong_received.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.info("WebSocket ping timeout for user_id=%d, connection_id=%s. Disconnecting.", user_id, connection_id)
                    await websocket.close(code=4000)
                    break
        except Exception:
            pass

    async def listen_redis_queue():
        try:
            queue_key = f"ws:user:{user_id}:{connection_id}"
            while True:
                # Poll Redis queue with 5s timeout
                pop_res = await redis.brpop(queue_key, timeout=5)
                if pop_res:
                    _, event_str = pop_res
                    try:
                        event = json.loads(event_str)
                        await websocket.send_json(event)
                    except Exception as send_err:
                        logger.warning("Failed to send WebSocket event to connection %s: %s", connection_id, send_err)
        except asyncio.CancelledError:
            pass
        except Exception as queue_err:
            logger.error("Error in listen_redis_queue for user_id=%d, connection_id=%s: %s", user_id, connection_id, queue_err)

    ping_task_handle = asyncio.create_task(ping_task())
    queue_task_handle = asyncio.create_task(listen_redis_queue())

    try:
        while True:
            data = await websocket.receive_text()
            # Check if it is a pong
            is_pong = False
            if data == "pong":
                is_pong = True
            else:
                try:
                    parsed = json.loads(data)
                    if parsed == "pong" or (isinstance(parsed, dict) and parsed.get("type") == "pong"):
                        is_pong = True
                except Exception:
                    pass
            if is_pong:
                pong_received.set()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Error in websocket loop for user_id=%d: %s", user_id, e)
    finally:
        ping_task_handle.cancel()
        queue_task_handle.cancel()
        try:
            await redis.srem(f"ws:connections:user:{user_id}", connection_id)
            await redis.delete(f"ws:heartbeat:{user_id}:{connection_id}")
            await redis.delete(f"ws:user:{user_id}:{connection_id}")
        except Exception as clean_err:
            logger.warning("Failed to clean Redis registry on disconnect: %s", clean_err)
        active_local_websockets.pop(connection_id, None)
        if user_id in active_connections and active_connections[user_id] == websocket:
            del active_connections[user_id]
        try:
            await websocket.close()
        except Exception:
            pass
