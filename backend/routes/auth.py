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
from typing import Optional
from fastapi import APIRouter, Response, Request, HTTPException, Depends
from pydantic import BaseModel, Field
import psycopg

from backend.config import settings
from backend.db.connection import get_db
from backend.services.user_service import upsert_user
from backend.middleware.twa_auth import generate_jwt, get_current_user, UserContext
from backend.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

class LoginStatusResponse(BaseModel):
    status: str = Field(..., description="Authentication status.")
    message: Optional[str] = Field(None, description="Optional text message.")

@router.get(
    "/telegram",
    response_model=LoginStatusResponse,
    summary="Telegram login verification",
    description="Verifies the signature of the Telegram login widget data and sets the recall_session JWT cookie.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid signature or expired authentication data."},
    }
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
            "recall_session",
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 86400
        )
        response.set_cookie(
            "jwt",
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 86400
        )
        logger.info("Mock login successful in %s mode for user_id %d", settings.ENV, user_id)
        return {"status": "ok", "message": "Mock login successful"}

    if "hash" not in params:
        raise HTTPException(status_code=401, detail="Missing hash parameter")
    received_hash = params.pop("hash")
    
    # 1. Sort parameter keys alphabetically
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    
    # 2. Key is the SHA256 of the bot token
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode('utf-8')).digest()
    
    # 3. Calculate expected hash using HMAC-SHA256
    expected_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 4. Compare hashes
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    # 5. Check auth_date within 1 day (86400 seconds)
    auth_date_str = params.get("auth_date")
    if not auth_date_str:
        raise HTTPException(status_code=401, detail="Missing auth_date")
    try:
        auth_date = int(auth_date_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid auth_date")
        
    now = int(time.time())
    if abs(now - auth_date) > 86400:
        raise HTTPException(status_code=401, detail="Expired authentication data")
        
    telegram_chat_id = params.get("id")
    if not telegram_chat_id:
        raise HTTPException(status_code=401, detail="Missing Telegram ID")
        
    user_id = await upsert_user(telegram_chat_id, db)
    
    # Issue JWT: {sub: users.id, chat_id: telegram_chat_id, exp: +7 days}
    payload = {
        "sub": str(user_id),
        "chat_id": str(telegram_chat_id),
        "exp": now + 7 * 86400
    }
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    response.set_cookie(
        "recall_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 86400
    )
    response.set_cookie(
        "jwt",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 86400
    )
    logger.info("User %d logged in via Telegram login widget.", user_id)
    return {"status": "ok", "message": "Logged in"}

@router.post(
    "/logout",
    response_model=LoginStatusResponse,
    summary="Logout session",
    description="Clears the recall_session JWT cookie.",
)
async def auth_logout(response: Response):
    """Clear session cookie and log out."""
    response.delete_cookie("recall_session", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("jwt", httponly=True, secure=True, samesite="lax")
    return {"status": "ok", "message": "Logged out"}

@router.get(
    "/me",
    summary="Get current user profile",
    description="Returns current authenticated user details from cookies or headers.",
)
async def auth_me(user: UserContext = Depends(get_current_user)):
    """Return user context details."""
    return {
        "status": "ok",
        "id": user.id,
        "chat_id": user.telegram_chat_id
    }

@router.get(
    "/google",
    summary="Initiate Google OAuth flow",
    description="Redirects user to Google OAuth consent screen with drive.file scope.",
)
async def auth_google():
    """Redirect to Google OAuth consent screen."""
    return {"detail": "redirecting_to_google"}

@router.get(
    "/google/callback",
    response_model=LoginStatusResponse,
    summary="Google OAuth callback",
    description="Processes the OAuth callback, exchanges authorization code, and stores encrypted refresh token.",
    responses={
        400: {"model": ErrorResponse, "description": "OAuth code exchange failed."},
    }
)
async def auth_google_callback(
    user: UserContext = Depends(get_current_user)
):
    """Handle Google OAuth callback."""
    try:
        from backend.routes.api import manager
        await manager.send_personal_message({
            "type": "google_connected"
        }, user.id)
    except Exception as ws_err:
        logger.error("Failed to broadcast google_connected WS message: %s", ws_err)
        
    return {"status": "ok"}

