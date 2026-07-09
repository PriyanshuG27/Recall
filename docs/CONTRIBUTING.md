# Contributing Guidelines & Developer Standards — Recall

Thank you for contributing to **Recall**! This document outlines the development principles, coding standards, pull request workflow, and mandatory workspace rules enforced in this repository.

---

## 1. Mandatory Workspace Architecture Rules

As defined in `AGENTS.md`, all contributions MUST strictly adhere to the following rules:

1. **Fixed Tech Stack**: FastAPI (backend) · React+Vite (frontend) · Neon PostgreSQL+pgvector+pg_trgm · Upstash Redis · Azure Student VM (AI) · Koyeb · Vercel. Do not introduce new dependencies without explicit justification.
2. **Zero Unparameterized SQL**: All database queries MUST use parameterized `$1, $2` placeholders. Direct string interpolation into SQL queries is prohibited.
3. **Webhook ACK Speed**: Telegram webhook handlers MUST return HTTP 200 ACK in **< 50 ms**. Heavy tasks must be pushed to the background queue (`recall:tasks`).
4. **AI Concurrency Cap**: `asyncio.Semaphore(3)` caps concurrent AI processing tasks across the worker and scheduler. Do not raise this limit without explicit justification.
5. **Fernet Encryption at Rest**: `raw_text` and `google_refresh_token` MUST be Fernet-encrypted before any database write.
6. **Timing-Safe Signatures**: All HMAC comparisons MUST use `hmac.compare_digest()`. Never use `==` for signature verification.
7. **Multi-Tenant Data Isolation**: Every user data query MUST include `WHERE user_id = <verified_user_id>`.

---

## 2. Pull Request Workflow

1. **Branching**: Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Verification**: Run backend tests (`make test`) and frontend tests (`cd frontend && npm test`).
3. **Submission**: Open a Pull Request targeting `main` with a description of changes and manual verification steps.


---

## 🔗 Related Documentation

[README](../README.md) · [INDEX](INDEX.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DATABASE](DATABASE.md) · [API](API.md) · [FEATURES](FEATURES.md)  
[DEVELOPMENT](DEVELOPMENT.md) · [DEPLOYMENT](DEPLOYMENT.md) · [SECURITY](SECURITY.md) · [TESTING](TESTING.md) · **CONTRIBUTING** · [DIAGRAMS](DIAGRAMS.md)
