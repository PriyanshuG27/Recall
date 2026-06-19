import os
import sys

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

if not DATABASE_URL:
    print("======================================================================", file=sys.stderr)
    print("VERIFICATION SKIPPED: DATABASE_URL is not set.", file=sys.stderr)
    print("======================================================================", file=sys.stderr)
    print("To run database DDL verification, please do one of the following:", file=sys.stderr)
    print("1. Set the DATABASE_URL environment variable in your terminal:", file=sys.stderr)
    print("   On Windows: $env:DATABASE_URL=\"postgresql://...\"", file=sys.stderr)
    print("2. Create a 'backend/.env.local' file with your DATABASE_URL:", file=sys.stderr)
    print("   DATABASE_URL=\"postgresql://...\"", file=sys.stderr)
    print("======================================================================", file=sys.stderr)
    sys.exit(0)  # Exit cleanly so it doesn't fail build scripts unnecessarily

try:
    import psycopg
except ImportError:
    print("Error: 'psycopg' library is not installed in the current environment.", file=sys.stderr)
    print("Please activate your virtual environment and run: pip install psycopg[binary]", file=sys.stderr)
    sys.exit(1)


def verify_db():
    print(f"Connecting to database to verify schema DDL...")
    redacted_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"Target host: {redacted_url}")
    
    try:
        conn = psycopg.connect(DATABASE_URL)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Please check your DATABASE_URL credentials and network settings.", file=sys.stderr)
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # 1. Verify Extensions
            print("\nChecking database extensions...")
            cur.execute("SELECT extname FROM pg_extension;")
            extensions = [row[0] for row in cur.fetchall()]
            print(f"Found extensions: {extensions}")
            
            missing_exts = []
            for ext in ["vector", "pg_trgm"]:
                if ext not in extensions:
                    missing_exts.append(ext)
            
            if missing_exts:
                print(f"FAIL: Missing required extension(s): {missing_exts}", file=sys.stderr)
                sys.exit(1)
            print("PASS: Required extensions (vector, pg_trgm) are active.")

            # 2. Verify Tables
            print("\nChecking database tables...")
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public';")
            tables = [row[0] for row in cur.fetchall()]
            print(f"Found tables: {tables}")
            
            required_tables = [
                "users", "items", "quizzes", "reminders", 
                "semantic_hubs", "processed_updates", "dead_letter_queue"
            ]
            missing_tables = [t for t in required_tables if t not in tables]
            
            if missing_tables:
                print(f"FAIL: Missing required table(s): {missing_tables}", file=sys.stderr)
                sys.exit(1)
            print(f"PASS: All {len(required_tables)} core tables are present.")

            # 3. Verify Partition Tables
            # Check partition sub-tables exist
            expected_partitions = ["items_y2026m06", "items_y2026m07"]
            missing_partitions = [p for p in expected_partitions if p not in tables]
            if missing_partitions:
                print(f"FAIL: Missing partition table(s): {missing_partitions}", file=sys.stderr)
                sys.exit(1)
            print("PASS: Monthly partitions (June + July 2026) are present.")

            # 4. Verify Indices on Items table
            print("\nChecking indices on the 'items' table...")
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='items';")
            indices = [row[0] for row in cur.fetchall()]
            print(f"Found indices: {indices}")
            
            required_indices = ["idx_items_user", "idx_items_embedding", "idx_items_text_gin"]
            missing_indices = [idx for idx in required_indices if idx not in indices]
            
            if missing_indices:
                print(f"FAIL: Missing index(es) on items table: {missing_indices}", file=sys.stderr)
                sys.exit(1)
            print("PASS: All required indices on 'items' table are present.")

            print("\n======================================================================")
            print("DDL SCHEMA VERIFICATION SUCCESSFUL!")
            print("======================================================================")

    except Exception as e:
        print(f"Error during schema verification: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    verify_db()
