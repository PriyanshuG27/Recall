import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Optional
import jwt  # PyJWT

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import settings
from backend.db.connection import get_db
import psycopg

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class UserContext(BaseModel):
    id: int
    telegram_chat_id: str


class CookieDict(dict):
    def items(self):
        return [
            ("Set-Cookie", "recall_session=; Max-Age=0; Path=/; SameSite=lax; HttpOnly; Secure"),
            ("Set-Cookie", "jwt=; Max-Age=0; Path=/; SameSite=lax; HttpOnly; Secure")
        ]


# ---------------------------------------------------------------------------
# JWT Helpers (using PyJWT)
# ---------------------------------------------------------------------------
def verify_jwt(token: str, secret: str) -> dict:
    """Verify and decode a JWT using PyJWT HS256."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError(str(e))




def generate_jwt(payload: dict, secret: str) -> str:
    """Generate a signed JWT using PyJWT HS256."""
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# TWA Verification Logic
# ---------------------------------------------------------------------------
def verify_twa_init_data(init_data_raw: str, bot_token: str) -> int:
    """
    Validates the Telegram Mini App initData HMAC and returns the user's Telegram ID.
    
    Security requirements:
      - Uses hmac.compare_digest for timing-attack resistance.
      - Never logs initData content (it contains sensitive user data).
      - Replay protection: auth_date must be within 1 hour (3600 seconds).
    """
    # 1. Parse URL-encoded key-value pairs.
    params = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
    
    # 2. Extract and remove 'hash' field.
    if 'hash' not in params:
        raise HTTPException(status_code=401, detail="Missing hash")
    received_hash = params.pop('hash')
    
    # 3. Sort remaining pairs alphabetically.
    sorted_pairs = sorted(params.items())
    
    # 4. Construct data_check_string = "key=value\nkey=value\n..."
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_pairs)
    
    # 5. secret_key = HMAC-SHA256(key=b"WebAppData", data=TELEGRAM_BOT_TOKEN.encode())
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    
    # 6. expected_hash = HMAC-SHA256(key=secret_key, data=data_check_string.encode()).hexdigest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    # 7. Compare expected_hash and received_hash.
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid hash")
        
    # 8. Validate: auth_date within 3600 seconds (1 hour).
    auth_date_str = params.get('auth_date')
    if not auth_date_str:
        raise HTTPException(status_code=401, detail="Missing auth_date")
    try:
        auth_date = int(auth_date_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid auth_date")
        
    now = int(time.time())
    if abs(now - auth_date) > 3600:
        raise HTTPException(status_code=401, detail="Expired auth_date")
        
    # 9. Extract user.id from initData.
    user_json = params.get('user')
    if not user_json:
        raise HTTPException(status_code=401, detail="Missing user field")
    try:
        user_data = json.loads(user_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=401, detail="Invalid user JSON")
        
    telegram_user_id = user_data.get('id')
    if telegram_user_id is None:
        raise HTTPException(status_code=401, detail="Missing user id")
        
    return telegram_user_id


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------
async def get_twa_user(
    request: Request,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """FastAPI dependency for verifying Telegram Web App initData in Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    if not auth_header.startswith("TelegramInitData "):
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    init_data_raw = auth_header[len("TelegramInitData "):]
    
    # Verify HMAC
    try:
        telegram_user_id = verify_twa_init_data(init_data_raw, settings.TELEGRAM_BOT_TOKEN)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Query database for user
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, telegram_chat_id FROM users WHERE telegram_chat_id = %s",
            (str(telegram_user_id),)
        )
        row = await cur.fetchone()
        
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    return UserContext(id=row[0], telegram_chat_id=str(row[1]))


async def get_jwt_user(
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """FastAPI dependency for verifying JWT stored in 'recall_session' or 'jwt' cookie."""
    token = request.cookies.get("recall_session") or request.cookies.get("jwt")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    try:
        payload = verify_jwt(token, settings.JWT_SECRET)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict())
        
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict())
        
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, telegram_chat_id FROM users WHERE id = %s",
            (int(user_id),)
        )
        row = await cur.fetchone()
        
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict())
        
    # Auto-refresh JWT if < 1 day (86400 seconds) remaining
    exp = payload.get("exp")
    if exp is not None:
        now = time.time()
        if exp - now < 86400:
            new_payload = {
                "sub": str(user_id),
                "chat_id": payload.get("chat_id"),
                "exp": int(now) + 7 * 86400
            }
            new_token = generate_jwt(new_payload, settings.JWT_SECRET)
            response.set_cookie(
                "recall_session",
                new_token,
                httponly=True,
                secure=settings.ENV != "development",
                samesite="lax",
                max_age=7 * 86400
            )
            response.set_cookie(
                "jwt",
                new_token,
                httponly=True,
                secure=settings.ENV != "development",
                samesite="lax",
                max_age=7 * 86400
            )
            
    return UserContext(id=row[0], telegram_chat_id=str(row[1]))


async def get_current_user(
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """
    Unified auth dependency for /api/* routes.
    
    Tries JWT cookie first; if missing, tries TWA header; if both missing: 401.
    Does not double-authenticate.
    """
    # 1. Try JWT cookie first
    jwt_cookie = request.cookies.get("recall_session") or request.cookies.get("jwt")
    if jwt_cookie is not None:
        return await get_jwt_user(request, response, db)
        
    # 2. If cookie is missing, check TWA header
    auth_header = request.headers.get("Authorization")
    if auth_header is not None and auth_header.startswith("TelegramInitData "):
        return await get_twa_user(request, db)
        
    # 3. If both are missing
    raise HTTPException(status_code=401, detail="Not authenticated")
