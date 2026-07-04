# 🚨 GLOBAL EXECUTION PROTOCOL (MANDATORY)

This protocol overrides every other instruction in this prompt.

---

# Phase 0 — Repository Loading (BLOCKING)

Before **any** reasoning, planning, implementation, refactoring, testing, tool usage, architecture decisions, or code generation:

## Step 1 — Load Repository Context

Read **completely**:

* `AGENTS.md`
* Every document under `/docs`
* Every document referenced by `AGENTS.md`
* Every dependency listed in **Required Dependencies**

Do **not** skip documents because they appear unrelated.

If **any** required file cannot be found or read:

* STOP immediately.
* Report the missing file(s).
* Do **not** continue.
* Wait for further instructions.

---

# Phase 1 — Dependency Loading (BLOCKING)

## Required Dependencies

Read the following dependencies completely before continuing:

* @python-pro
* @postgres-best-practices
* @database-cli

Read every dependency **from beginning to end**.

Do **not**:

* skim
* summarize without reading
* rely on memory
* assume previous prompts already loaded them

Every architectural, implementation, security, performance, testing, and design decision must comply with these dependencies.

---

# Phase 2 — Verification (REQUIRED)

Before writing **any** code, output exactly:

```text
### Repository Verification

✅ AGENTS.md loaded
✅ Repository documentation loaded
✅ @python-pro loaded
✅ @postgres-best-practices loaded
✅ @database-cli loaded
```

Only mark a dependency as loaded if it was actually located, opened, and completely read.

---

# Phase 3 — Compliance Summary (REQUIRED)

For **every** dependency and repository document:

Provide:

* 3–5 important implementation rules
* the relevant section/reference
* how those rules affect this implementation

Do **not** continue if this cannot be done.

---

# Phase 4 — Implementation Plan (REQUIRED)

Before generating code provide:

* Architecture overview
* Files to modify/create
* Backend changes
* Frontend changes
* Database changes
* API changes
* Scheduler changes (if any)
* Security considerations
* Performance considerations
* Testing strategy

---

# GLOBAL REPOSITORY RULES

These rules apply regardless of the prompt.

## Architecture

* Fixed stack:

  * FastAPI
  * React + Vite
  * Neon PostgreSQL + pgvector + pg_trgm
  * Upstash Redis
  * Modal GPU
  * Render
  * Vercel

* Do not introduce new libraries without explicit justification.

* Prefer stdlib and already-approved packages.

---

## Database

* Parameterized SQL only.
* Never build SQL via string interpolation.
* Every user query must be scoped to the authenticated user.
* Use transactions where required.
* Respect existing indexes.

---

## Security

* Never expose:

  * TELEGRAM_BOT_TOKEN
  * JWT_SECRET
  * FERNET_KEY

* Never log:

  * plaintext
  * tokens
  * secrets
  * encrypted values

* Encrypt before DB write where required.

* Secret comparisons must always use:

```python
hmac.compare_digest(...)
```

Never use `==`.

---

## Authentication

Every `/api/*` endpoint must authenticate using the project's existing authentication middleware.

Never duplicate authentication logic.

---

## Performance

Maintain repository targets including:

* Webhook ACK <50 ms
* Canvas 60 FPS @ 500 nodes
* Vector search <10 ms
* Text search <5 ms

Heavy work must remain asynchronous.

---

## Error Handling

* Specific exception handling only.
* No broad silent failures.
* Never expose stack traces.
* Preserve repository retry behavior.
* Scheduler jobs must configure the required `misfire_grace_time`.

---

## Testing

Every new function requires corresponding unit tests.

Backend:

* pytest

Frontend:

* Vitest

Mock:

* AI services
* Telegram
* Redis
* Google APIs
* Chrome APIs
* External services

### IMPORTANT

Create or update tests.

**Do NOT execute them.**

---

## Coding Rules

* Reuse existing project abstractions.
* Avoid duplicate logic.
* Keep implementations modular.
* Follow repository conventions.
* Prefer composition over duplication.

---

# Failure Policy

If any dependency, AGENTS.md, or required documentation cannot be loaded:

* STOP.
* Do not generate code.
* Do not guess.
* Report what is missing.
* Wait for further instructions.

Implementation before completing all loading and verification phases is considered invalid.

---

# TASK

## PROMPT 099 — Partition Manager CLI Script

**Skills:** `python-pro`, `postgres-best-practices`, `database-cli`

```
Create `backend/scripts/partition_manager.py` — an automated CLI utility for managing PostgreSQL range partitions on the `items` table.

Create `backend/scripts/partition_manager.py`:
```python
import argparse
import asyncio
from datetime import datetime
from dateutil.relativedelta import relativedelta
from backend.db.connection import get_db

async def create_partitions(months: int, dry_run: bool):
    now = datetime.utcnow()
    async with get_db() as conn:
        async with conn.cursor() as cur:
            for i in range(months):
                target = now + relativedelta(months=i)
                year_str = target.strftime("%Y")
                month_str = target.strftime("%m")
                start_date = f"{year_str}-{month_str}-01"
                
                next_month = target + relativedelta(months=1)
                end_date = f"{next_month.strftime('%Y')}-{next_month.strftime('%m')}-01"
                
                table_name = f"items_y{year_str}m{month_str}"
                ddl = f"CREATE TABLE IF NOT EXISTS {table_name} PARTITION OF items FOR VALUES FROM ('{start_date}') TO ('{end_date}');"
                
                print(f"[+] DDL: {ddl}")
                if not dry_run:
                    await cur.execute(ddl)
                    print(f"[✓] Created partition {table_name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL Partition Manager CLI")
    parser.add_argument("--action", choices=["create", "list", "detach"], required=True)
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.action == "create":
        asyncio.run(create_partitions(args.months, args.dry_run))
```

Rules:
- CLI script must require confirmation prompt before executing DDL alterations unless `--yes` flag is passed.
- All DDL queries must use parameterised/validated identifiers preventing SQL injection.

Gate Check:
[ ] `--action create` creates correct monthly partition tables and indices
[ ] `--action list` outputs current partition status and row counts
[ ] Dry-run mode (`--dry-run`) displays SQL statements without executing
```
