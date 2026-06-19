import os
import sys
from datetime import datetime, date
from cryptography.fernet import Fernet

# ------------------------------------------------------------------------------
# ENVIRONMENT & SECURITY CHECKS
# ------------------------------------------------------------------------------

# Attempt to load dotenv if available (for local execution convenience)
try:
    from dotenv import load_dotenv
    # Load .env.local first, fallback to .env
    if os.path.exists("backend/.env.local"):
        load_dotenv("backend/.env.local")
    elif os.path.exists(".env.local"):
        load_dotenv(".env.local")
    else:
        load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
FERNET_KEY = os.getenv("FERNET_KEY")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.", file=sys.stderr)
    sys.exit(1)

# CRITICAL: Prevent running against production database.
# The URL must contain 'dev' or 'test' (e.g., in the Neon branch name or database name).
if "dev" not in DATABASE_URL.lower() and "test" not in DATABASE_URL.lower():
    print("CRITICAL SECURITY ERROR: DATABASE_URL does not contain 'dev' or 'test'.", file=sys.stderr)
    print("Seeding is only allowed against development/test databases to prevent data loss.", file=sys.stderr)
    sys.exit(1)

if not FERNET_KEY:
    print("Error: FERNET_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

try:
    fernet = Fernet(FERNET_KEY.encode())
except Exception as e:
    print(f"Error: Invalid FERNET_KEY. {e}", file=sys.stderr)
    sys.exit(1)


# Import psycopg. We handle potential ImportError gracefully.
try:
    import psycopg
except ImportError:
    print("Error: 'psycopg' library (psycopg3) is not installed.", file=sys.stderr)
    print("Please install it using 'pip install \"psycopg[binary]\"' before seeding.", file=sys.stderr)
    sys.exit(1)


def encrypt_text(text: str) -> str:
    """Encrypt text using Fernet AES-128."""
    if not text:
        return ""
    return fernet.encrypt(text.encode()).decode()


def seed_database():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")  # Redact credentials in logs
    
    # Connect to the DB (psycopg3 uses sync connect by default)
    try:
        conn = psycopg.connect(DATABASE_URL)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # 1. Clear existing seed data (optional but helpful for clean runs)
            print("Cleaning existing data...")
            cur.execute("DELETE FROM users WHERE telegram_chat_id IN ('111111111', '222222222', '333333333');")
            
            # 2. Insert 3 test users
            print("Seeding 3 test users...")
            users_data = [
                ("111111111", 0, 5, date(2026, 6, 19)),
                ("222222222", -300, 3, date(2026, 6, 19)),
                ("333333333", 120, 0, None)
            ]
            
            user_ids = []
            for chat_id, tz_offset, streak, last_act in users_data:
                # Parameterised statement
                cur.execute(
                    """
                    INSERT INTO users (telegram_chat_id, timezone_offset, streak_count, last_activity_date)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (chat_id, tz_offset, streak, last_act)
                )
                user_ids.append(cur.fetchone()[0])
            
            print(f"Created user IDs: {user_ids}")
            
            # 3. Seed 10 items for each user
            print("Seeding 10 items per user...")
            
            item_templates = [
                {
                    "source_type": "text",
                    "title": "Thoughts on Agentic Workflows",
                    "raw_text": "We need to build systems that plan, act, observe, and reflect. The loop is key.",
                    "summary": "Notes on planning, acting, observing, and reflecting in agentic workflows.",
                    "tags": ["ai", "agents", "software"]
                },
                {
                    "source_type": "url",
                    "source_url": "https://example.com/postgres-indexes",
                    "title": "Deep Dive into Postgres Indexes",
                    "raw_text": "GIN indexes are great for full-text search, and HNSW indexes enable fast vector search.",
                    "summary": "Technical review of PostgreSQL GIN and pgvector HNSW indexing capabilities.",
                    "tags": ["postgres", "database", "vector"]
                },
                {
                    "source_type": "voice",
                    "title": "Voice Memo: Morning Braindump",
                    "raw_text": "Remember to check the rate limit settings on Redis tomorrow. We need to make sure the sliding window works.",
                    "summary": "Audio transcript reminder about Redis sliding window rate limits configuration.",
                    "tags": ["redis", "rate-limiting", "todo"]
                },
                {
                    "source_type": "pdf",
                    "title": "Attention Is All You Need Paper",
                    "raw_text": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
                    "summary": "Abstract summary of the Transformer neural network architecture paper.",
                    "tags": ["deep-learning", "transformers", "paper"]
                },
                {
                    "source_type": "image",
                    "title": "Receipt: Coffee & Keyboard",
                    "raw_text": "Date: 2026-06-19 Coffee: $4.50 Keyboard: $120.00 Total: $124.50",
                    "summary": "OCR scan details of a coffee and keyboard purchase receipt.",
                    "tags": ["receipt", "finance", "ocr"]
                },
                {
                    "source_type": "text",
                    "title": "FastAPI Best Practices",
                    "raw_text": "Always use dependency injection for database sessions and redact secrets in settings representation.",
                    "summary": "Guidelines on using dependency injection and setting security in FastAPI.",
                    "tags": ["fastapi", "python", "security"]
                },
                {
                    "source_type": "url",
                    "source_url": "https://example.com/neon-serverless",
                    "title": "Neon Serverless Postgres Architecture",
                    "raw_text": "Neon separates storage and compute. Compute nodes are stateless and scale to zero.",
                    "summary": "Overview of Neon's separation of compute and storage for scaling to zero.",
                    "tags": ["postgres", "neon", "cloud"]
                },
                {
                    "source_type": "voice",
                    "title": "Voice Memo: Feature ideas for Recall",
                    "raw_text": "What if we add spaced repetition flashcards automatically generated by the LLM?",
                    "summary": "Idea brainstorm for LLM-driven spaced repetition flashcard generation.",
                    "tags": ["ideas", "spaced-repetition", "quizzes"]
                },
                {
                    "source_type": "pdf",
                    "title": "OAuth 2.0 Security Best Practices",
                    "raw_text": "Use the state parameter to protect against CSRF attacks and always use the drive.file scope.",
                    "summary": "Security analysis of OAuth 2.0 and best practices for scopes.",
                    "tags": ["oauth", "security", "google"]
                },
                {
                    "source_type": "text",
                    "title": "Louvain Community Detection",
                    "raw_text": "Louvain modularity optimization is a simple, heuristic method for finding communities in large graphs.",
                    "summary": "Mathematical explanation of modularity maximization using the Louvain algorithm.",
                    "tags": ["graphs", "louvain", "clustering"]
                }
            ]
            
            for user_id in user_ids:
                for idx, template in enumerate(item_templates):
                    # Parameterised statement
                    cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, tags, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            user_id,
                            template["source_type"],
                            template.get("source_url"),
                            encrypt_text(template["raw_text"]),  # Fernet encrypted
                            template["summary"],                 # plaintext summary
                            f"{template['title']} (User {user_id})",
                            template["tags"],
                            datetime.now()
                        )
                    )
            
            # Commit the transaction
            conn.commit()
            print("Successfully seeded database.")

    except Exception as e:
        conn.rollback()
        print(f"Error during seeding: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
