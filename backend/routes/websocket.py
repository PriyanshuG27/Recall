import logging
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.middleware.twa_auth import verify_jwt
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# In-memory registry: {user_id: WebSocket}
active_connections: dict[int, WebSocket] = {}

async def broadcast(user_id: int, event: dict) -> None:
    """Broadcast an event to the user's active WebSocket connection."""
    websocket = active_connections.get(user_id)
    if websocket:
        try:
            await websocket.send_json(event)
        except Exception:
            # Clean up on failure to send
            if user_id in active_connections and active_connections[user_id] == websocket:
                del active_connections[user_id]

@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    # Validate the JWT
    try:
        payload = verify_jwt(token, settings.JWT_SECRET)
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

    # Register the connection (last connection wins)
    if user_id in active_connections:
        try:
            await active_connections[user_id].close(code=1000)
        except Exception:
            pass
    active_connections[user_id] = websocket

    # Immediately send the connected event
    try:
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id
        })
    except Exception:
        if user_id in active_connections and active_connections[user_id] == websocket:
            del active_connections[user_id]
        return

    # Ping/pong maintenance loop
    pong_received = asyncio.Event()

    async def ping_task():
        try:
            while True:
                await asyncio.sleep(30.0)
                pong_received.clear()
                await websocket.send_json({"type": "ping"})
                try:
                    await asyncio.wait_for(pong_received.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.info("WebSocket ping timeout for user_id=%d. Disconnecting.", user_id)
                    await websocket.close(code=4000)
                    break
        except Exception:
            pass

    ping_task_handle = asyncio.create_task(ping_task())

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
        if user_id in active_connections and active_connections[user_id] == websocket:
            del active_connections[user_id]
        try:
            await websocket.close()
        except Exception:
            pass
