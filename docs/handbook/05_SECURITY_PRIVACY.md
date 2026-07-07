# Chapter 5: Security, Encryption & Privacy Layer

## 1. Introduction
Recall accepts arbitrary user content, which intrinsically includes sensitive documents, credentials, medical reports, and internal work artifacts. A robust security boundary is paramount. This chapter defines the encryption mechanisms, privacy filters, authentication rules, and adversarial safeguards required to operate Recall safely as a multi-tenant application.

## 2. Current Recall implementation
Recall currently employs Fernet AES-128 symmetric encryption for highly sensitive fields (`items.raw_text`, `users.google_refresh_token`) before writing to PostgreSQL. Authentication relies on HMAC-SHA256 signature verification for Telegram WebApp data and JWTs for API sessions. A safety module (`safety.py`) uses regex to mask basic PII (emails, phone numbers) and detect prompt injection attempts (e.g., XML breakout tokens).

## 3. Problems
*   **Inconsistent Security Layers:** The system splits prompt validation across `safety.py` (regex keywords) and `security/filter.py` (length limits), and completely bypasses these checks for certain AI operations (e.g., Quiz/Insight endpoints).
*   **Plaintext Cache Leaks:** The Redis cache currently stores hashed queries, but raw text can sometimes leak into cache keys or values if not carefully monitored.
*   **Unauthenticated Webhooks:** The main Telegram webhook endpoint (`backend/routes/webhook.py`) does not verify the `X-Telegram-Bot-Api-Secret-Token`, making it vulnerable to request forgery.
*   **Weak Content Classification:** All documents are treated equally. There is no tagging mechanism to classify a document as "Confidential," which would prevent it from being sent to external LLMs.

## 4. Design Goals
*   **Zero-Trust Multi-Tenancy:** Hardcode tenant isolation (`user_id`) at the lowest SQL execution level.
*   **Defense-in-Depth AI:** Sanitize inputs before they hit the LLM, and sanitize outputs before they hit the database or user.
*   **Data at Rest Encryption:** Encrypt all raw knowledge payloads so that database dumps are useless to attackers.
*   **Unified Safety Boundary:** Route all AI tasks through a single, unified security filter.

## 5. Architecture
1.  **Authentication Layer:** JWTs (via httpOnly, Secure, SameSite=Lax cookies) for the WebApp, and HMAC `compare_digest` for Telegram webhooks.
2.  **Encryption Layer:** Symmetric AES-128 encryption applied automatically in the ORM/persistence layer.
3.  **Privacy Layer:** PII masking regex engine strips identifiers before text is sent to third-party APIs (Groq/Gemini).
4.  **Adversarial Filter:** Blocks `system:` overrides, `</context>` escapes, and Markdown backtick breakouts to prevent LLM jailbreaks.

## 6. Data Flow
1.  Telegram sends a webhook POST.
2.  The API validates the `X-Telegram-Bot-Api-Secret-Token` header.
3.  The payload is queued and picked up by the worker.
4.  The worker runs the text through `SecurityLayer.validate_prompt` (checking length and injection patterns).
5.  `mask_pii()` strips out emails/phone numbers from the payload before it goes to the AI Provider.
6.  The AI returns a summary.
7.  The original raw text is encrypted via `encryption.py` (`Fernet.encrypt`).
8.  The encrypted raw text and plaintext summary are saved to PostgreSQL.

## 7. Diagrams

```mermaid
flowchart TD
    A[Incoming Request] --> B{Authentication}
    B -- Webhook --> C[Verify HMAC Secret]
    B -- API --> D[Verify JWT Cookie]
    
    C & D --> E[Security Boundary Filter]
    E --> F{Check Injection & Length}
    F -- Fail --> G[Drop & Log]
    F -- Pass --> H[PII Masking]
    
    H --> I[AI Provider]
    I --> J[Encryption Layer (Fernet)]
    J --> K[(PostgreSQL)]
```

## 8. Interfaces
*   **Security Layer Interface:**
    ```python
    class SecurityLayer:
        def validate_prompt(self, prompt: str) -> bool:
            # Enforce 500k char limit and run check_prompt_injection()
            pass
            
        def mask_sensitive_data(self, text: str) -> str:
            # Apply PII masking regex
            pass
    ```

## 9. Database Changes
*   Ensure all `raw_text` and `token` columns are strictly typed as `TEXT` to accommodate base64-encoded Fernet strings, not `VARCHAR`.
*   Maintain the strict foreign key relationships on `user_id` across all tables.

## 10. Folder Structure
*   `backend/services/ai_cascade/security/filter.py`: The unified security layer.
*   `backend/services/encryption.py`: Fernet AES-128 utilities.
*   `backend/routes/auth.py`: JWT and Telegram WebApp HMAC logic.

## 11. API Changes
*   **Webhook Auth:** Enforce the `X-Telegram-Bot-Api-Secret-Token` check on `/webhook/telegram`. Reject unauthenticated requests with HTTP 401.
*   **Cookie Security:** Ensure all authentication cookies enforce `Secure=True` in production and `SameSite="Lax"`.

## 12. Migration Strategy
1.  Generate a permanent `FERNET_KEY` and inject it into the production environment.
2.  Deploy the webhook HMAC validation immediately to prevent trivial request forgery.
3.  Merge `safety.py` into `security/filter.py` and wrap the single filter around *all* AI operations, not just summaries.
4.  Implement a background script to re-encrypt any legacy plaintext rows if they exist.

## 13. Rollback Strategy
If PII masking is too aggressive (e.g., destroying valid code snippets containing `@`), the masking regex can be updated dynamically or temporarily disabled via an environment variable `DISABLE_PII_MASKING=true` without reverting the entire deployment.

## 14. Performance
*   **Encryption Overhead:** Fernet encryption is fast but adds CPU overhead. Ensure it runs in the background worker, not blocking the web request.
*   **Regex Engine:** Complex prompt injection regexes can cause ReDoS (Regular Expression Denial of Service). All regexes must be strictly bounded and tested against pathological inputs.

## 15. Failure Modes
*   **Lost Fernet Key:** Catastrophic data loss. The `FERNET_KEY` must be securely backed up in an external secrets manager (e.g., AWS Secrets Manager, Vercel Env).
*   **Injection Bypass:** If a new jailbreak technique circumvents the filter, the fallback is that the database write strictly enforces parameterized SQL (`$1`), preventing SQL injection even if the LLM output is hostile.

## 16. Security Considerations
*   **SQL Injection:** Addressed via 100% usage of `asyncpg` parameterized queries. Zero string interpolation is permitted.
*   **Cross-User Data Leakage:** Every `SELECT`, `UPDATE`, and `DELETE` on user data must enforce `WHERE user_id = $user_id`.

## 17. Complexity Analysis
*   **Time Complexity:** AES-128 encryption is O(N) where N is the length of the text. Regex scanning is O(N).
*   **Space Complexity:** Encrypted strings inflate payload sizes by roughly 33% due to base64 encoding and block padding.

## 18. Tradeoffs
*   **External LLMs vs. Privacy:** Sending data to Groq/Gemini sacrifices absolute privacy for intelligence. PII masking mitigates this, but a future toggle for "Local Processing Only" (routing to a local Ollama model) is the ultimate privacy tradeoff.

## 19. Alternatives Considered
*   **Client-Side Encryption:** Rejected. Would completely break the AI's ability to summarize and search documents on the server.
*   **Role-Based Access Control (RBAC):** Rejected. Recall is a single-user-per-account model; complex RBAC is unnecessary overhead.

## 20. Final Recommendation
Consolidate all safety and security checks into the single `SecurityLayer`. Mandate webhook authentication and enforce strict `WHERE user_id` checks on every database interaction. Treat the `FERNET_KEY` as the single most critical secret in the system.

## 21. Implementation Checklist
*   [ ] Unify `safety.py` and `security/filter.py`.
*   [ ] Implement `X-Telegram-Bot-Api-Secret-Token` validation on webhooks.
*   [ ] Route Quiz, Insight, and RAG pipelines through the `SecurityLayer`.
*   [ ] Verify `httpOnly` and `Secure` flags on JWT cookies.

## 22. Future Improvements
*   Implement a "Confidential" sensitivity tag that strictly routes the document to a local, air-gapped LLM model.
*   Add automated secret scanning (detecting AWS keys, passwords) to the PII masking layer.

## 23. Version
1.0.0

## 24. Priority
P0 - Absolute Criticality

## 25. Estimated Engineering Effort
4 Developer Days.
