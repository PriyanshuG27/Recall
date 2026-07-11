"""
backend/routes/auth.py
======================
Authentication routes for Recall.
Handles Telegram Login Widget verification, Google OAuth, and session logout.
"""

import logging
import hashlib
import hmac
import time
import base64
from typing import Optional
from fastapi import APIRouter, Response, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
import psycopg
import httpx

from backend.config import settings
from backend.db.connection import get_db
from backend.services.user_service import upsert_user
from backend.services.encryption import encrypt
from backend.middleware.twa_auth import generate_jwt, verify_jwt, get_current_user, UserContext
from backend.models.schemas import ErrorResponse

from backend.services.rate_limiter import rate_limit_by_route

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

class LoginStatusResponse(BaseModel):
    status: str = Field(..., description="Authentication status.")
    message: Optional[str] = Field(None, description="Optional text message.")

@router.get(
    "/telegram",
    response_model=LoginStatusResponse,
    summary="Telegram login verification",
    description="Verifies the signature of the Telegram login widget data and sets the atrium_session JWT cookie.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid signature or expired authentication data."},
    },
    dependencies=[Depends(rate_limit_by_route("login", limit=5, window=60, burst=2))]
)
async def auth_telegram(
    request: Request,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Verify Telegram login credentials and set session cookie."""
    params = dict(request.query_params)
    
    # Check for mock login bypass in development/testing mode
    if settings.ENV != "production" and params.get("mock") == "true":
        telegram_chat_id = params.get("id") or "12345"
        user_id = await upsert_user(telegram_chat_id, db)
        
        payload = {
            "sub": str(user_id),
            "chat_id": str(telegram_chat_id),
            "exp": int(time.time()) + 7 * 86400
        }
        token = generate_jwt(payload, settings.JWT_SECRET)
        
        response.set_cookie(
            "atrium_session",
            token,
            httponly=True,
            secure=settings.ENV != "development",
            samesite="lax",
            max_age=7 * 86400
        )
        response.set_cookie(
            "jwt",
            token,
            httponly=True,
            secure=settings.ENV != "development",
            samesite="lax",
            max_age=7 * 86400
        )
        logger.info("Mock login successful in %s mode for user_id %d", settings.ENV, user_id)
        return {"status": "ok", "message": "Mock login successful"}

    if "hash" not in params:
        raise HTTPException(status_code=401, detail="Authentication failed")
    received_hash = params.pop("hash")
    
    # 1. Sort parameter keys alphabetically
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    
    # 2. Key is the SHA256 of the bot token
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode('utf-8')).digest()
    
    # 3. Calculate expected hash using HMAC-SHA256
    expected_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 4. Compare hashes using constant-time comparison
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    # 5. Check auth_date within 1 day (86400 seconds)
    auth_date_str = params.get("auth_date")
    if not auth_date_str:
        raise HTTPException(status_code=401, detail="Authentication failed")
    try:
        auth_date = int(auth_date_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    now = int(time.time())
    if abs(now - auth_date) > 86400:
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    telegram_chat_id = params.get("id")
    if not telegram_chat_id:
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    user_id = await upsert_user(telegram_chat_id, db)
    
    # Save first_name and username (only if changed to avoid redundant WAL writes and lock contention)
    first_name = params.get("first_name")
    username = params.get("username")
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT first_name, username FROM users WHERE id = %s;",
            (user_id,)
        )
        row = await cur.fetchone()
        if row is None or row[0] != first_name or row[1] != username:
            await cur.execute(
                "UPDATE users SET first_name = %s, username = %s WHERE id = %s;",
                (first_name, username, user_id)
            )
            await db.commit()
            logger.info("Updated Telegram profile details for user %d", user_id)
    
    # Issue JWT
    payload = {
        "sub": str(user_id),
        "chat_id": str(telegram_chat_id),
        "exp": now + 7 * 86400
    }
    token = generate_jwt(payload, settings.JWT_SECRET)
    cookie_secure = settings.ENV != "development"

    # Detect callback vs redirect mode:
    # Widget callback mode calls this via fetch() — no Accept: text/html header
    accept = request.headers.get("Accept", "")
    is_fetch = "text/html" not in accept

    if is_fetch:
        # Callback mode: return JSON, set cookie on response object
        response.set_cookie("atrium_session", token, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)
        response.set_cookie("jwt", token, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)
        logger.info("User %d logged in via Telegram widget (callback mode).", user_id)
        return {"status": "ok", "user_id": user_id}
    else:
        # Redirect mode (legacy): redirect browser to dashboard
        redirect_url = f"{settings.WEBSITE_URL}/dashboard"
        redirect_response = RedirectResponse(url=redirect_url)
        redirect_response.set_cookie("atrium_session", token, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)
        redirect_response.set_cookie("jwt", token, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)
        logger.info("User %d logged in via Telegram widget (redirect mode).", user_id)
        return redirect_response

# ── Bot-session browser login ─────────────────────────────────────────────────
# Flow: browser calls /init → shows deep link → user opens bot in Telegram
#       → bot stores user_id under token → browser polls /poll → gets cookie

@router.get(
    "/bot-session/init",
    summary="Initialise a bot-session browser login token",
    dependencies=[Depends(rate_limit_by_route("bot-session-init", limit=5, window=60))]
)
async def bot_session_init():
    """Generate a one-time OTP + token for browser login via Telegram bot."""
    import secrets, random
    from backend.services.redis_client import redis as _redis
    token = secrets.token_urlsafe(24)
    otp = f"{random.randint(0, 999999):06d}"   # 6-digit zero-padded
    # token → pending (polled by browser)
    await _redis.setex(f"bot_web_login_pending:{token}", 300, "pending")
    # otp → token (looked up by bot webhook when user sends the code)
    await _redis.setex(f"bot_web_login_otp:{otp}", 300, token)
    bot_username = getattr(settings, "BOT_USERNAME", "AtriumHub_bot")
    return {"token": token, "otp": otp, "bot_username": bot_username, "expires_in": 300}


@router.get("/bot-session/poll", summary="Poll bot-session login completion")
async def bot_session_poll(
    token: str,
    response: Response,
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Returns 202 while waiting; 200 + sets session cookie once the bot confirms the token."""
    from backend.services.redis_client import redis as _redis
    confirmed_user_id = await _redis.get(f"bot_web_login:{token}")
    if not confirmed_user_id:
        return Response(status_code=202)

    user_id = int(confirmed_user_id)

    async with db.cursor() as cur:
        await cur.execute("SELECT telegram_chat_id FROM users WHERE id = %s;", (user_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="User not found")
    chat_id = str(row[0])

    now = int(time.time())
    payload = {"sub": str(user_id), "chat_id": chat_id, "exp": now + 7 * 86400}
    token_jwt = generate_jwt(payload, settings.JWT_SECRET)
    cookie_secure = settings.ENV != "development"

    response.set_cookie("atrium_session", token_jwt, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)
    response.set_cookie("jwt", token_jwt, httponly=True, secure=cookie_secure, samesite="lax", max_age=604800)

    await _redis.delete(f"bot_web_login:{token}")
    await _redis.delete(f"bot_web_login_pending:{token}")

    logger.info("Bot-session login complete for user %d (chat_id %s)", user_id, chat_id)
    return {"status": "ok", "user_id": user_id, "chat_id": chat_id}


@router.post(
    "/logout",
    response_model=LoginStatusResponse,
    summary="Logout session",
    description="Clears the atrium_session JWT cookie and blacklists the token.",
)
async def auth_logout(request: Request, response: Response):
    """Clear session cookie, blacklist token, and log out."""
    token = request.cookies.get("atrium_session") or request.cookies.get("jwt")
    auth_header = request.headers.get("Authorization")
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if token:
        try:
            import jwt
            from backend.config import settings
            from backend.services.redis_client import redis
            # Decode to find expiry time
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
            exp = payload.get("exp")
            if exp:
                remaining_seconds = int(exp - time.time())
                if remaining_seconds > 0:
                    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    await redis.setex(f"jwt:blacklist:{token_hash}", remaining_seconds, "1")
        except Exception as e:
            logger.warning("Failed to blacklist JWT token on logout: %s", e)

    response.delete_cookie("atrium_session", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("jwt", httponly=True, secure=True, samesite="lax")
    return {"status": "ok", "message": "Logged out"}

@router.get(
    "/me",
    summary="Get current user profile",
    description="Returns current authenticated user details from cookies or headers.",
)
async def auth_me(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Return user context details."""
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT google_refresh_token, google_last_sync FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
    has_drive = row is not None and row[0] is not None
    google_last_sync = row[1] if row else None
    if google_last_sync and google_last_sync.tzinfo is None:
        from datetime import timezone
        google_last_sync = google_last_sync.replace(tzinfo=timezone.utc)
    token = request.cookies.get("jwt") or request.cookies.get("atrium_session")
    return {
        "status": "ok",
        "id": user.id,
        "chat_id": user.telegram_chat_id,
        "drive_connected": has_drive,
        "google_last_sync": google_last_sync.isoformat() if google_last_sync else None,
        "token": token
    }

@router.get(
    "/google",
    summary="Initiate Google OAuth flow",
    description="Redirects user to Google OAuth consent screen with drive.file scope.",
)
async def auth_google(
    request: Request,
    response: Response,
    chat_id: Optional[str] = None,
    popup: Optional[bool] = None,
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Redirect to Google OAuth consent screen with drive.file scope."""
    target_chat_id = chat_id
    if not target_chat_id:
        try:
            user = await get_current_user(request, response, db)
            target_chat_id = user.telegram_chat_id
        except HTTPException:
            raise HTTPException(status_code=401, detail="Missing telegram_chat_id or not authenticated")
            
    if not target_chat_id:
        raise HTTPException(status_code=401, detail="Missing telegram_chat_id")
        
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on the server")
        
    payload = {
        "chat_id": str(target_chat_id),
        "exp": int(time.time()) + 600
    }
    if popup:
        payload["popup"] = True
    state = generate_jwt(payload, settings.JWT_SECRET)
    
    import urllib.parse
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    
    oauth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=oauth_url)

@router.get(
    "/google/callback",
    summary="Google OAuth callback",
    description="Processes the OAuth callback, exchanges authorization code, and stores encrypted refresh token.",
)
async def auth_google_callback(
    request: Request,
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Handle Google OAuth callback."""
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    
    if not state:
        raise HTTPException(status_code=401, detail="Missing state parameter")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
        
    try:
        # Timing-safe signature check
        parts = state.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid state token format")
            
        signing_input = f"{parts[0]}.{parts[1]}".encode('utf-8')
        key = settings.JWT_SECRET.encode('utf-8')
        expected_sig_bytes = hmac.new(key, signing_input, hashlib.sha256).digest()
        
        expected_sig = base64.urlsafe_b64encode(expected_sig_bytes).decode('utf-8').replace('=', '')
        if not hmac.compare_digest(expected_sig, parts[2]):
            raise HTTPException(status_code=401, detail="State signature mismatch")
            
        # Verify expiration and claims
        payload = verify_jwt(state, settings.JWT_SECRET)
    except ValueError:
        # Expired token raises ValueError
        raise HTTPException(status_code=401, detail="Expired state token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid state token")
        
    chat_id = payload.get("chat_id")
    if not chat_id:
        raise HTTPException(status_code=401, detail="Invalid state payload")
        
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on the server")
        
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Google OAuth token exchange HTTP error: %s", e.response.text)
            raise HTTPException(status_code=400, detail="Google OAuth code exchange failed")
        except Exception as e:
            logger.error("Google OAuth token exchange error: %s", e)
            raise HTTPException(status_code=400, detail="Google OAuth code exchange failed")
            
    token_data = resp.json()
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        logger.error("No refresh token returned by Google OAuth")
        raise HTTPException(status_code=400, detail="No refresh token returned")
        
    # Encrypt the refresh token
    encrypted_refresh_token = encrypt(refresh_token)
    
    # Store the encrypted refresh token
    user_id = await upsert_user(chat_id, db)
    async with db.cursor() as cur:
        await cur.execute(
            """
            UPDATE users
            SET google_refresh_token = %s
            WHERE telegram_chat_id = %s;
            """,
            (encrypted_refresh_token, str(chat_id))
        )
        await db.commit()
        
    # Broadcast WebSocket event
    try:
        from backend.routes.api import manager
        await manager.send_personal_message({
            "type": "google_connected"
        }, user_id)
    except Exception as ws_err:
        logger.error("Failed to broadcast google_connected WS message: %s", ws_err)
        
    # Send Telegram message
    telegram_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    telegram_payload = {
        "chat_id": str(chat_id),
        "text": "✅ Google Drive connected! Your knowledge will be backed up daily."
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            tg_resp = await client.post(telegram_url, json=telegram_payload)
            tg_resp.raise_for_status()
    except Exception as tg_err:
        logger.error("Failed to send Telegram message: %s", tg_err)
        
    # Redirect to WEBSITE_URL/dashboard
    is_popup = payload.get("popup", False)
    if is_popup:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=f"""
        <html>
          <body>
            <script>
              if (window.opener) {{
                window.opener.postMessage("google_connected", "{settings.WEBSITE_URL}");
              }}
              window.close();
            </script>
          </body>
        </html>
        """)

    redirect_url = f"{settings.WEBSITE_URL}/dashboard"
    return RedirectResponse(url=redirect_url)

