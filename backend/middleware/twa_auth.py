import base64
import hashlib
import logging

logger = logging.getLogger(__name__)
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
            ("Set-Cookie", "atrium_session=; Max-Age=0; Path=/; SameSite=lax; HttpOnly; Secure"),
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
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """FastAPI dependency for verifying Telegram Web App initData in Authorization header.

    Auto-registers new users on first open and sets a JWT session cookie so
    subsequent requests work without needing the TelegramInitData header.
    """
    from backend.services.user_service import upsert_user

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not auth_header.startswith("TelegramInitData "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    init_data_raw = auth_header[len("TelegramInitData "):]

    # Verify HMAC signature
    try:
        telegram_user_id = verify_twa_init_data(init_data_raw, settings.TELEGRAM_BOT_TOKEN)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Auto-register new users; return existing user id for known users
    try:
        user_id = await upsert_user(str(telegram_user_id), db)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Optionally update display name / username from initData
    try:
        params = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
        user_json = params.get('user')
        if user_json:
            user_data = json.loads(user_json)
            first_name = user_data.get('first_name')
            username = user_data.get('username')
            if first_name or username:
                async with db.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET first_name = COALESCE(%s, first_name), username = COALESCE(%s, username) WHERE id = %s;",
                        (first_name, username, user_id)
                    )
                    await db.commit()
    except Exception:
        pass

    # Issue a persistent JWT session cookie so the browser stays logged in
    payload = {
        "sub": str(user_id),
        "chat_id": str(telegram_user_id),
        "exp": int(time.time()) + 7 * 86400,
    }
    token = generate_jwt(payload, settings.JWT_SECRET)
    cookie_secure = settings.ENV != "development"
    response.set_cookie(
        "atrium_session",
        token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=7 * 86400,
    )
    response.set_cookie(
        "jwt",
        token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=7 * 86400,
    )

    return UserContext(id=user_id, telegram_chat_id=str(telegram_user_id))


async def get_jwt_user_by_token(
    token: str,
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection,
    set_cookies: bool = True
) -> UserContext:
    # Check JWT Blacklist in Redis
    try:
        from backend.services.redis_client import redis
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        is_blacklisted = await redis.get(f"jwt:blacklist:{token_hash}")
        if is_blacklisted:
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.", headers=CookieDict() if set_cookies else None)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to verify JWT blacklist check: %s", e)

    try:
        payload = verify_jwt(token, settings.JWT_SECRET)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict() if set_cookies else None)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict() if set_cookies else None)
        
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, telegram_chat_id FROM users WHERE id = %s",
            (int(user_id),)
        )
        row = await cur.fetchone()
        
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=CookieDict() if set_cookies else None)
        
    if set_cookies:
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
                    "atrium_session",
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


async def get_jwt_user(
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """FastAPI dependency for verifying JWT stored in 'atrium_session' or 'jwt' cookie."""
    token = request.cookies.get("atrium_session") or request.cookies.get("jwt")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await get_jwt_user_by_token(token, request, response, db, set_cookies=True)


async def get_current_user(
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
) -> UserContext:
    """
    Unified auth dependency for /api/* routes.

    Tries JWT cookie first; if missing, tries TWA header or Bearer header; if all missing: 401.
    """
    # 1. Try JWT cookie first
    jwt_cookie = request.cookies.get("atrium_session") or request.cookies.get("jwt")
    if jwt_cookie is not None:
        return await get_jwt_user_by_token(jwt_cookie, request, response, db, set_cookies=True)

    # 2. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header is not None:
        if auth_header.startswith("TelegramInitData "):
            # Pass response so get_twa_user can set the session cookie
            return await get_twa_user(request, response, db)
        elif auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            return await get_jwt_user_by_token(token, request, response, db, set_cookies=False)

    # 3. If all are missing
    raise HTTPException(status_code=401, detail="Not authenticated")
