# AUTH_ARCHITECTURE — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Overview

Three independent auth layers stack on top of each other. Layer 1 is always active. Layers 2a/2b are surface-dependent. Layer 3 is optional (adds Drive capability).

```
┌────────────────────────────────────────────────┐
│ Layer 3: Google OAuth (drive.file)             │ optional
├────────────────────────────────────────────────┤
│ Layer 2a: TWA HMAC   │ Layer 2b: Login Widget  │ surface-dependent
├────────────────────────────────────────────────┤
│ Layer 1: Telegram chat_id (primary identity)   │ always
└────────────────────────────────────────────────┘
```

---

## Layer 1 — Telegram chat_id Identity

- Every Telegram user has a unique numeric `chat.id`.
- On first `/start`, backend creates a `users` row with `telegram_chat_id = str(chat.id)`.
- No password, no email, no signup form.
- All items, quizzes, reminders, and hubs reference `users.id` (internal surrogate key).

```
User sends /start
    -> POST /webhook receives update
    -> Extract chat.id from update.message.chat.id
    -> INSERT INTO users (telegram_chat_id) ON CONFLICT DO NOTHING
    -> User row created (or silently skipped if already exists)
```

---

## Layer 2a — Telegram Web App (TWA) HMAC

Used when the web dashboard is opened **inside Telegram** as a Mini App.

```
Sequence:
    Browser (Telegram TWA context)
        |
        | window.Telegram.WebApp.initData  (URL-encoded string)
        |
        v
    Frontend -> POST /api/* with initData in header
        |
        v
    Backend:
        1. Parse initData key-value pairs
        2. Remove 'hash' field; sort remaining pairs alphabetically
        3. Construct data_check_string = "key=value\nkey=value\n..."
        4. secret_key = HMAC-SHA256(key="WebAppData", data=TELEGRAM_BOT_TOKEN)
        5. expected_hash = HMAC-SHA256(key=secret_key, data=data_check_string)
        6. Compare expected_hash == initData['hash'] (constant-time)
        7. Check initData['auth_date'] is within 1 hour (replay protection)
        8. Extract user.id -> look up users row -> attach to request context
```

Failure: 401 Unauthorized.

---

## Layer 2b — Website Telegram Login Widget (JWT)

Used when the web dashboard is opened **outside Telegram** in a browser.

```
Sequence:
    Browser loads Recall website
        |
        | Telegram Login Widget script renders button
        |
        v
    User clicks "Log in with Telegram"
        -> Telegram opens auth popup
        -> User approves
        -> Telegram redirects to GET /auth/telegram?id=...&hash=...&auth_date=...
        |
        v
    Backend GET /auth/telegram:
        1. Collect all query params except 'hash'
        2. Sort alphabetically; join as "key=value\n" string
        3. secret_key = SHA256(TELEGRAM_BOT_TOKEN)  [note: SHA256, not HMAC here]
        4. expected_hash = HMAC-SHA256(key=secret_key, data=check_string)
        5. Compare expected_hash == params['hash']
        6. Check auth_date within 1 day
        7. Look up / create users row by telegram_chat_id
        8. Issue JWT: {sub: users.id, chat_id: telegram_chat_id, exp: +7 days}
        9. Set JWT in httpOnly cookie; redirect to dashboard
```

JWT properties:
- Signed with `JWT_SECRET` (HS256).
- 7-day expiry.
- httpOnly, Secure, SameSite=Lax cookie.
- Validated on every `/api/*` request.

---

## Layer 3 — Google OAuth (Drive Sync)

Triggered from either Telegram bot (`/connect_drive` command) or website (Connect Drive button). Both surfaces sync state via WebSocket.

```
Sequence (bot-triggered):
    User sends /connect_drive to bot
        -> Bot sends OAuth URL: GET /auth/google
        -> Backend generates state = JWT {chat_id, exp: +10 min}
        -> Redirects to Google with scope=drive.file, state=<token>

    User authenticates with Google
        -> Google redirects to GET /auth/google/callback?code=...&state=...

    Backend callback:
        1. Validate state JWT (prevents CSRF)
        2. Exchange code for tokens via Google token endpoint
        3. Encrypt refresh_token with Fernet
        4. UPDATE users SET google_refresh_token = <encrypted> WHERE telegram_chat_id = <from state>
        5. Broadcast to WS /ws/{token}: {type: "google_connected"}
        6. Bot sends confirmation message; web dashboard updates icon
```

```
Sequence (website-triggered):
    User clicks Connect Drive button
        -> Frontend opens /auth/google in popup
        -> Same callback flow
        -> WS event updates button state in real time without page reload
```

Scope: `https://www.googleapis.com/auth/drive.file` — can only access files Recall created.

---

## Auth Surface Matrix

| Surface | Layer 1 | Layer 2 | Layer 3 |
|---------|---------|---------|---------|
| Telegram bot | chat_id in update | None (Telegram itself authenticates) | Optional |
| TWA (in Telegram) | chat_id | 2a: HMAC initData | Optional |
| Website (browser) | chat_id from widget | 2b: Login Widget JWT | Optional |

---

## Token Lifetimes

| Token | Lifetime | Storage |
|-------|----------|---------|
| Telegram chat_id | Permanent | users table |
| TWA initData | 1 hour (replay window) | Client memory |
| JWT (website session) | 7 days | httpOnly cookie |
| Google access token | 1 hour | Never persisted |
| Google refresh token | Until revoked | users table (Fernet encrypted) |
| OAuth state token | 10 minutes | Signed JWT in redirect |
