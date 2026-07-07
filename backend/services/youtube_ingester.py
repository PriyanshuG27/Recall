"""
backend/services/youtube_ingester.py
====================================
Service layer for YouTube URL ingestion in Recall.
"""

import os
import uuid
import logging
import asyncio
import yt_dlp
from psycopg import AsyncConnection

from backend.services.encryption import encrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade, ai_cascade

logger = logging.getLogger(__name__)

def _sync_yt_dlp_extract_info(url: str, ydl_opts: dict) -> dict | None:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def _sync_yt_dlp_download(url: str, ydl_opts: dict) -> None:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

async def ingest_youtube(url: str, user_id: int, db: AsyncConnection, user_context: str = None) -> int:
    """
    Ingests a YouTube URL.
    Attempts to download the audio track via yt-dlp, transcribes using Whisper,
    summarises, and embeds.
    If downloading or transcribing fails, falls back to saving a minimal bookmark
    using the extracted video title.
    """
    logger.info("================================================================================")
    logger.info("[YouTube Ingestion] Starting ingestion pipeline for User ID: %d", user_id)
    logger.info("[YouTube Ingestion] Target YouTube URL: %s", url)
    logger.info("================================================================================")

    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    # 1. Extract metadata first (so we have the title even if download fails)
    video_title = "YouTube Video"
    video_duration = 0
    try:
        logger.info("[YouTube Ingestion] Extracting metadata title and duration via yt-dlp...")
        ydl_opts_meta = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _sync_yt_dlp_extract_info, url, ydl_opts_meta)
        if info:
            video_title = info.get("title") or "YouTube Video"
            video_duration = info.get("duration") or 0
        logger.info("  [YouTube Ingestion] Metadata resolved. Title: '%s', Duration: %d seconds", video_title, video_duration)
    except Exception as meta_err:
        logger.warning("  [YouTube Ingestion] Metadata extraction failed: %s", meta_err)

    # 2. Attempt audio download if video duration <= 20 minutes (1200s) to keep within quotas
    temp_filename = f"{uuid.uuid4()}"
    temp_path_template = os.path.join(tmp_dir, temp_filename)
    audio_path = None
    
    if video_duration > 1200:
        logger.warning("[YouTube Ingestion] Video duration (%d seconds) exceeds the 20-minute limit. Skipping audio download fallback.", video_duration)
    else:
        logger.info("[YouTube Ingestion] Downloading audio track using yt-dlp...")
        ydl_opts_dl = {
            'format': 'worstaudio/worst',
            'outtmpl': temp_path_template + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sync_yt_dlp_download, url, ydl_opts_dl)
                
            # Find the downloaded file
            for f in os.listdir(tmp_dir):
                if f.startswith(temp_filename):
                    audio_path = os.path.join(tmp_dir, f)
                    logger.info("  [YouTube Ingestion] Audio file downloaded to: %s", audio_path)
                    break
        except Exception as dl_err:
            logger.warning("  [YouTube Ingestion] Audio download failed: %s", dl_err)

    # 3. Process the audio if downloaded
    transcript = None
    if audio_path and os.path.exists(audio_path):
        try:
            # Check file size (must be <= 25 MB for Whisper API)
            file_size = os.path.getsize(audio_path)
            logger.info("  [YouTube Ingestion] Downloaded audio file size: %.2f MB", file_size / (1024 * 1024))
            if file_size > 25 * 1024 * 1024:
                raise ValueError("Downloaded YouTube audio file exceeds 25 MB limit.")

            logger.info("[YouTube Ingestion] Dispatching audio to AI Cascade for Whisper transcription...")
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            # Transcribe via AI cascade
            cascade = AICascade()
            transcript = await cascade.transcribe(audio_bytes)
            if not transcript:
                raise ValueError("Transcription of YouTube audio failed.")
            logger.info("  [YouTube Ingestion] Whisper transcription succeeded. Length: %d chars", len(transcript))
        except Exception as proc_err:
            logger.warning("  [YouTube Ingestion] Audio processing failed: %s. Trying caption fallback.", proc_err)
        finally:
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.info("  [YouTube Ingestion] Cleaned up temporary local audio file.")
                except Exception:
                    pass

    # 4. If no transcript obtained, try youtube-transcript-api as a fallback
    if not transcript:
        logger.info("[YouTube Ingestion] Whisper audio transcription failed or skipped. Trying subtitle/caption fallback...")
        try:
            # Parse video ID from URL
            video_id = None
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[1].split("?")[0]
            elif "embed/" in url:
                video_id = url.split("embed/")[1].split("?")[0]

            if video_id:
                logger.info("  [YouTube Ingestion] Found video ID: %s. Querying youtube-transcript-api...", video_id)
                from youtube_transcript_api import YouTubeTranscriptApi
                api = YouTubeTranscriptApi()
                transcript_list = api.list(video_id)
                
                # Check preferred languages first
                preferred_langs = ["en", "en-US", "en-GB"]
                selected_transcript = None
                for lang in preferred_langs:
                    try:
                        selected_transcript = transcript_list.find_transcript([lang])
                        break
                    except Exception:
                        pass
                
                # If no preferred lang found, get the first available transcript
                if not selected_transcript:
                    try:
                        selected_transcript = next(iter(transcript_list))
                    except Exception:
                        pass

                if selected_transcript:
                    logger.info("  [YouTube Ingestion] Found caption transcript in language: %s", selected_transcript.language_code)
                    segments = selected_transcript.fetch()
                    transcript = " ".join([segment.text for segment in segments])
                else:
                    logger.warning("  [YouTube Ingestion] No captions found in any language for video ID: %s", video_id)
            else:
                logger.warning("  [YouTube Ingestion] Could not parse video ID from URL.")
        except Exception as trans_err:
            logger.warning("  [YouTube Ingestion] Caption fallback extraction failed: %s", trans_err)

    # 5. If we have a transcript (from audio or captions), process and save it
    if transcript:
        try:
            # Sanitize transcript to correct misheard tech/design tool names
            try:
                logger.info("  [YouTube Ingestion] Sanitizing transcript for misheard entity names...")
                cascade = AICascade()
                transcript = await cascade.sanitize_transcript(transcript)
            except Exception as e:
                logger.warning("  [YouTube Ingestion] Transcript sanitization failed: %s", e)

            summarizer_input = transcript
            if user_context:
                summarizer_input = f"[User's Note/Context: {user_context}]\n" + transcript
            cascade = AICascade()
            ai_res = await cascade.summarise(summarizer_input, user_id=user_id)
            summary = ai_res.get("summary") or f"Summary of video: {transcript[:200]}..."
            tags = ai_res.get("tags") or ["youtube"]
            context_prompt = ai_res.get("context_prompt")
            normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]

            logger.info("[YouTube Ingestion] Creating vector embedding for the transcribed text...")
            raw_text = f"YouTube: {url}\nTitle: {video_title}\nTranscript:\n{transcript}"
            embedding = await embed_text(raw_text)
            encrypted_raw_text = encrypt(raw_text)

            logger.info("[YouTube Ingestion] Inserting new item into Database (Fernet encrypted)...")
            if hasattr(db, "connection"):
                db_ctx = db.connection()
            else:
                class DummyContext:
                    async def __aenter__(self):
                        return db
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass
                db_ctx = DummyContext()

            async with db_ctx as conn:
                if hasattr(db, "connection"):
                    await conn.execute("SET statement_timeout = '30s'")
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_prompt)
                        VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s, %s)
                        RETURNING id;
                        """,
                        (user_id, url, encrypted_raw_text, summary, video_title, embedding, normalized_tags, context_prompt)
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RuntimeError("DB INSERT returned no ID.")
                    item_id = row[0]
                    await conn.commit()

            logger.info("[YouTube Ingestion] SUCCESS: Ingested YouTube Item ID=%d for User ID=%d", item_id, user_id)
            logger.info("================================================================================")
            return item_id
        except Exception as proc_err:
            logger.error("[YouTube Ingestion] Database insertion or encryption failed: %s. Falling back to bookmark.", proc_err)

    # 6. Fallback: Save as a bookmark
    logger.warning("[YouTube Ingestion] Falling back to bookmark placeholder for: %s", url)
    bookmark_summary = f"Could not process this YouTube video. Saved as a placeholder bookmark."
    bookmark_title = f"Bookmark: {video_title}"
    bookmark_tags = ["bookmark", "youtube"]
    val = 1.0 / (384 ** 0.5)
    mock_emb = [val] * 384
    encrypted_raw = encrypt(url)

    if hasattr(db, "connection"):
        db_ctx = db.connection()
    else:
        class DummyContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        db_ctx = DummyContext()

    async with db_ctx as conn:
        if hasattr(db, "connection"):
            await conn.execute("SET statement_timeout = '30s'")
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
                VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s)
                RETURNING id;
                """,
                (user_id, url, encrypted_raw, bookmark_summary, bookmark_title, mock_emb, bookmark_tags)
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Database INSERT for bookmark fallback failed.")
            item_id = row[0]
            await conn.commit()
        
    logger.info("[YouTube Ingestion] SUCCESS (Fallback): Ingested bookmark placeholder ID=%d for User ID=%d", item_id, user_id)
    logger.info("================================================================================")
    return item_id




async def _download_audio_from_url(download_url: str, dest_path: str) -> bool:
    """
    Downloads a direct audio/video URL (e.g. from Cobalt) to a local file.
    Returns True on success.
    """
    import httpx
    logger.info("  [Instagram Ingestion] Starting audio download from: %s", download_url)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", download_url) as resp:
                if resp.status_code != 200:
                    logger.warning("  [Instagram Ingestion] Cobalt download URL returned HTTP status %d", resp.status_code)
                    return False
                with open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        logger.info("  [Instagram Ingestion] Audio file successfully downloaded locally to: %s", dest_path)
        return True
    except Exception as e:
        logger.warning("  [Instagram Ingestion] Audio file download failed: %s", e)
        return False


async def _try_cobalt(url: str, cobalt_api_url: str) -> str | None:
    """
    Calls a self-hosted Cobalt instance to get a direct media download URL.
    Returns the download URL string on success, or None on failure.
    cobalt_api_url should be the base URL of the instance, e.g. https://cobalt.example.com
    """
    import httpx
    endpoint = cobalt_api_url.rstrip("/") + "/"
    payload = {
        "url": url,
        "downloadMode": "audio",   # audio-only — we only need it for transcription
        "filenameStyle": "basic",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    logger.info("  [Instagram Ingestion] Submitting URL to Cobalt API endpoint: %s", endpoint)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning("  [Instagram Ingestion] Cobalt API returned HTTP %d for URL: %s", resp.status_code, url)
                return None
            data = resp.json()
            status = data.get("status")
            if status in ("stream", "redirect", "tunnel"):
                download_url = data.get("url")
                if download_url:
                    logger.info("  [Instagram Ingestion] Cobalt successfully resolved URL! (Type: %s)", status)
                    return download_url
            logger.warning("  [Instagram Ingestion] Cobalt API returned unexpected response status '%s' — JSON body: %s", status, data)
            return None
    except Exception as e:
        logger.warning("  [Instagram Ingestion] Cobalt API request failed: %s", e)
        return None


async def _scrape_instagram_meta(url: str) -> tuple[str | None, str | None]:
    """Fallback scraping for Instagram using crawler User-Agent to extract og:title and og:description."""
    import httpx
    from bs4 import BeautifulSoup
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_codedoc.pdf)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                title = None
                description = None
                for meta in soup.find_all("meta"):
                    prop = meta.get("property") or meta.get("name")
                    if prop == "og:title":
                        title = meta.get("content")
                    elif prop in ("og:description", "description"):
                        description = meta.get("content")
                
                if not title and soup.title and soup.title.string:
                    title = soup.title.string.strip()
                    
                return title, description
    except Exception as e:
        logger.warning("  [Instagram Ingestion] Crawler fallback scraping failed: %s", e)
    return None, None


async def ingest_instagram(url: str, user_id: int, db: AsyncConnection, user_context: str = None) -> int:

    """
    Ingests an Instagram URL (Reel / Post).

    Pipeline:
      1. yt-dlp direct (with cookies / browser settings)
      2. Cobalt fallback
      3. Bookmark fallback
    """
    import random
    from backend.config import settings

    logger.info("================================================================================")
    logger.info("[Instagram Ingestion] Starting ingestion pipeline for User ID: %d", user_id)
    logger.info("[Instagram Ingestion] Target Instagram URL: %s", url)
    logger.info("================================================================================")

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp_dir = os.path.join(backend_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    audio_path: str | None = None

    # ------------------------------------------------------------------ #
    # Tier 1: yt-dlp direct (with cookies / browser settings)            #
    # ------------------------------------------------------------------ #
    logger.info("[Instagram Ingestion] Tier 1: Attempting download via direct yt-dlp...")
    temp_filename = str(uuid.uuid4())
    temp_path_template = os.path.join(tmp_dir, temp_filename)

    # 1. Try B64 Env Var Cookies
    import base64
    import tempfile
    
    ig_cookies_b64 = os.environ.get("IG_COOKIES_B64") or getattr(settings, "IG_COOKIES_B64", None)
    temp_b64_cookies_path = None
    has_b64_cookies = False
    
    if ig_cookies_b64:
        try:
            cleaned_b64 = ig_cookies_b64.strip()
            cookie_bytes = base64.b64decode(cleaned_b64)
            fd, temp_b64_cookies_path = tempfile.mkstemp(suffix=".txt", prefix="ig_cookies_")
            with os.fdopen(fd, "wb") as f:
                f.write(cookie_bytes)
            has_b64_cookies = True
            logger.info("  [Instagram Ingestion] Found valid IG_COOKIES_B64 env variable. Decoding to Netscape format.")
        except Exception as e:
            logger.warning("  [Instagram Ingestion] Failed to decode IG_COOKIES_B64: %s", e)
            if temp_b64_cookies_path and os.path.exists(temp_b64_cookies_path):
                try:
                    os.remove(temp_b64_cookies_path)
                except Exception:
                    pass
                temp_b64_cookies_path = None

    # 2. Try cookies.json on disk
    cookies_json_path = os.path.join(backend_dir, "cookies.json")
    temp_cookies_txt = os.path.join(tmp_dir, f"cookies_{uuid.uuid4()}.txt")
    has_json_cookies = False
    if not has_b64_cookies:
        has_json_cookies = _convert_cookies_json_to_netscape(cookies_json_path, temp_cookies_txt)
        if has_json_cookies:
            logger.info("  [Instagram Ingestion] Found valid cookies.json on disk. Converting to Netscape format.")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": temp_path_template + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if has_b64_cookies:
        ydl_opts["cookiefile"] = temp_b64_cookies_path
    elif has_json_cookies:
        ydl_opts["cookiefile"] = temp_cookies_txt
    else:
        browser_for_cookies = getattr(settings, "BROWSER_FOR_COOKIES", None)
        if browser_for_cookies:
            logger.info("  [Instagram Ingestion] Fallback: loading cookies directly from browser: %s", browser_for_cookies)
            ydl_opts["cookiesfrombrowser"] = (browser_for_cookies,)
        else:
            logger.info("  [Instagram Ingestion] Proceeding unauthenticated.")

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _sync_yt_dlp_download, url, ydl_opts
        )
        for fname in os.listdir(tmp_dir):
            if fname.startswith(temp_filename):
                audio_path = os.path.join(tmp_dir, fname)
                logger.info("[Instagram Ingestion] Tier 1 SUCCESS: Audio downloaded via direct yt-dlp: %s", audio_path)
                break
    except Exception as dl_err:
        logger.warning("[Instagram Ingestion] Tier 1 FAILURE: Direct yt-dlp download failed: %s", dl_err)
    finally:
        # Clean up temporary cookie files
        if temp_b64_cookies_path and os.path.exists(temp_b64_cookies_path):
            try:
                os.remove(temp_b64_cookies_path)
                logger.info("  [Instagram Ingestion] Cleaned up temporary base64 cookies file.")
            except Exception:
                pass
        if os.path.exists(temp_cookies_txt):
            try:
                os.remove(temp_cookies_txt)
                logger.info("  [Instagram Ingestion] Cleaned up temporary Netscape cookies file.")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Tier 2: Cobalt Fallback                                              #
    # ------------------------------------------------------------------ #
    if not audio_path:
        cobalt_url = getattr(settings, "COBALT_API_URL", None)
        if cobalt_url:
            logger.info("[Instagram Ingestion] Tier 2: Attempting fallback download via self-hosted Cobalt...")
            download_url = await _try_cobalt(url, cobalt_url)
            if download_url:
                dest = os.path.join(tmp_dir, f"{uuid.uuid4()}.mp3")
                ok = await _download_audio_from_url(download_url, dest)
                if ok and os.path.exists(dest):
                    audio_path = dest
                    logger.info("[Instagram Ingestion] Tier 2 SUCCESS: Audio downloaded via Cobalt.")
                else:
                    logger.warning("[Instagram Ingestion] Tier 2 WARNING: Cobalt URL resolved, but final audio stream download failed.")
            else:
                logger.warning("[Instagram Ingestion] Tier 2 FAILURE: Cobalt failed to resolve media URL.")
        else:
            logger.info("[Instagram Ingestion] Tier 2 SKIPPED: COBALT_API_URL environment variable is not configured.")

    # ------------------------------------------------------------------ #
    # Transcribe + save (Tiers 1 & 2 share the same processing block)     #
    # ------------------------------------------------------------------ #
    transcript: str | None = None
    if audio_path and os.path.exists(audio_path):
        try:
            file_size = os.path.getsize(audio_path)
            logger.info("[Instagram Ingestion] Downloaded audio file size: %.2f MB", file_size / (1024 * 1024))
            if file_size > 50 * 1024 * 1024:
                raise ValueError("Downloaded file exceeds the max limit of 50 MB.")
            
            logger.info("[Instagram Ingestion] Dispatching audio to AI Cascade for Whisper transcription...")
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            cascade = AICascade()
            transcript = await cascade.transcribe(audio_bytes)
            if not transcript:
                raise ValueError("Whisper transcription returned empty result.")
            logger.info("[Instagram Ingestion] Whisper transcription succeeded. Length: %d chars", len(transcript))
        except Exception as proc_err:
            logger.warning("[Instagram Ingestion] Processing or transcribing Instagram audio failed: %s", proc_err)
        finally:
            try:
                os.remove(audio_path)
                logger.info("  [Instagram Ingestion] Cleaned up temporary local audio file: %s", audio_path)
            except Exception:
                pass

    if transcript:
        try:
            # Sanitize transcript to correct misheard tech/design tool names
            try:
                logger.info("  [Instagram Ingestion] Sanitizing transcript for misheard entity names...")
                cascade = AICascade()
                transcript = await cascade.sanitize_transcript(transcript)
            except Exception as e:
                logger.warning("  [Instagram Ingestion] Transcript sanitization failed: %s", e)

            # 1. Fetch metadata first (best effort — no crash on failure)
            video_title = "Instagram Video"
            video_description = None
            try:
                logger.info("[Instagram Ingestion] Extracting metadata title via yt-dlp...")
                loop = asyncio.get_running_loop()
                info = await loop.run_in_executor(
                    None, _sync_yt_dlp_extract_info, url, {"quiet": True, "no_warnings": True, "extract_flat": True}
                )
                if info:
                    raw_title = info.get("title") or info.get("description") or ""
                    video_title = (raw_title[:97] + "...") if len(raw_title) > 100 else raw_title or "Instagram Video"
                    video_description = info.get("description")
                logger.info("[Instagram Ingestion] Metadata extraction title resolved: '%s'", video_title)
            except Exception as meta_err:
                logger.info("  [Instagram Ingestion] Metadata extract via yt-dlp failed, trying crawler fallback... Error: %s", meta_err)
                scraped_title, scraped_desc = await _scrape_instagram_meta(url)
                if scraped_title:
                    video_title = (scraped_title[:97] + "...") if len(scraped_title) > 100 else scraped_title
                if scraped_desc:
                    video_description = scraped_desc
                logger.info("  [Instagram Ingestion] Crawler fallback resolved title: '%s', description length: %d", video_title, len(video_description) if video_description else 0)

            # 2. Run summarizer with metadata context prepended to the transcript
            logger.info("[Instagram Ingestion] Running AI Cascade summarizer & tag generator...")
            cascade = AICascade()
            
            summarizer_input = ""
            if user_context:
                summarizer_input += f"[User's Note/Context: {user_context}]\n"
            if video_title and video_title != "Instagram Video":
                summarizer_input += f"Video Title: {video_title}\n"
            if video_description:
                summarizer_input += f"Video Description/Caption: {video_description}\n"
            summarizer_input += f"Audio Transcript:\n{transcript}"
            
            ai_res = await cascade.summarise(summarizer_input, user_id=user_id)
            summary = ai_res.get("summary") or f"Instagram Reel: {transcript[:200]}..."
            tags = ai_res.get("tags") or ["instagram", "reel"]
            context_prompt = ai_res.get("context_prompt")
            normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]

            logger.info("[Instagram Ingestion] Creating vector embedding for the transcribed text...")
            raw_text = f"Instagram: {url}\nTitle: {video_title}\nTranscript:\n{transcript}"
            embedding = await embed_text(raw_text)
            encrypted_raw_text = encrypt(raw_text)

            logger.info("[Instagram Ingestion] Inserting new item into Database (Fernet encrypted)...")
            if hasattr(db, "connection"):
                db_ctx = db.connection()
            else:
                class DummyContext:
                    async def __aenter__(self):
                        return db
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass
                db_ctx = DummyContext()

            async with db_ctx as conn:
                if hasattr(db, "connection"):
                    await conn.execute("SET statement_timeout = '30s'")
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_prompt)
                        VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s, %s)
                        RETURNING id;
                        """,
                        (user_id, url, encrypted_raw_text, summary, video_title, embedding, normalized_tags, context_prompt),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RuntimeError("DB INSERT returned no ID.")
                    item_id = row[0]
                    await conn.commit()

            logger.info("[Instagram Ingestion] SUCCESS: Ingested Instagram Item ID=%d for User ID=%d", item_id, user_id)
            logger.info("================================================================================")
            return item_id
        except Exception as save_err:
            logger.error("[Instagram Ingestion] Database insertion or encryption failed: %s. Falling back to bookmark.", save_err)

    if not transcript:
        # Fallback metadata ingestion
        logger.info("[Instagram Ingestion] Audio ingestion failed, trying metadata scraper fallback...")
        try:
            scraped_title, scraped_desc = await _scrape_instagram_meta(url)
            if scraped_title or scraped_desc:
                logger.info("[Instagram Ingestion] Scraped metadata fallback success. Title: '%s', Description length: %d", scraped_title, len(scraped_desc) if scraped_desc else 0)
                
                video_title = scraped_title or "Instagram Video"
                video_description = scraped_desc
                
                logger.info("[Instagram Ingestion] Running AI Cascade summarizer & tag generator on scraped metadata...")
                cascade = AICascade()
                summarizer_input = (
                     "[METADATA-ONLY FALLBACK: Audio/video transcription was unavailable. "
                     "Do NOT hallucinate or assume any details of the video content. "
                     "Summarize ONLY the provided video title and description/caption below. "
                     "Explicitly state that the transcription was unavailable.]\n"
                 )
                if user_context:
                    summarizer_input += f"[User's Note/Context: {user_context}]\n"
                if video_title and video_title != "Instagram Video":
                    summarizer_input += f"Video Title: {video_title}\n"
                if video_description:
                    summarizer_input += f"Video Description/Caption: {video_description}\n"
                
                ai_res = await cascade.summarise(summarizer_input, user_id=user_id)
                summary = ai_res.get("summary") or f"Instagram Reel (Metadata): {video_description[:200] if video_description else ''}"
                tags = ai_res.get("tags") or ["instagram", "reel"]
                context_prompt = ai_res.get("context_prompt")
                normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
                
                # Now we need to save it!
                raw_text = f"Instagram: {url}\nTitle: {video_title}\nDescription: {video_description or ''}"
                embedding = await embed_text(raw_text)
                encrypted_raw_text = encrypt(raw_text)
                
                if hasattr(db, "connection"):
                    db_ctx = db.connection()
                else:
                    class DummyContext:
                        async def __aenter__(self): return db
                        async def __aexit__(self, *a): pass
                    db_ctx = DummyContext()
                    
                async with db_ctx as conn:
                    if hasattr(db, "connection"):
                        await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_prompt)
                            VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s, %s)
                            RETURNING id;
                            """,
                            (user_id, url, encrypted_raw_text, summary, video_title, embedding, normalized_tags, context_prompt),
                        )
                        row = await cur.fetchone()
                        if not row:
                            raise RuntimeError("DB INSERT returned no ID.")
                        item_id = row[0]
                        await conn.commit()
                logger.info("[Instagram Ingestion] SUCCESS (Metadata Fallback): Ingested Instagram Item ID=%d for User ID=%d", item_id, user_id)
                return item_id
        except Exception as e:
            logger.error("[Instagram Ingestion] Metadata fallback failed: %s", e)

    # ------------------------------------------------------------------ #
    # Tier 3: Bookmark fallback                                            #
    # ------------------------------------------------------------------ #
    logger.warning("[Instagram Ingestion] Tier 3: Falling back to bookmark placeholder for: %s", url)
    val = 1.0 / (384 ** 0.5)
    mock_emb = [val] * 384
    encrypted_raw = encrypt(url)

    fallback_summary = "Could not process this Instagram Reel. Saved as a placeholder bookmark."
    if user_context:
        fallback_summary = f"[User's Note/Context: {user_context}] " + fallback_summary

    if hasattr(db, "connection"):
        db_ctx = db.connection()
    else:
        class DummyContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        db_ctx = DummyContext()

    async with db_ctx as conn:
        if hasattr(db, "connection"):
            await conn.execute("SET statement_timeout = '30s'")
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
                VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s)
                RETURNING id;
                """,
                (
                    user_id, url, encrypted_raw,
                    fallback_summary,
                    "Bookmark: Instagram Video",
                    mock_emb,
                    ["bookmark", "instagram"]
                )
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Database INSERT for bookmark fallback failed.")
            item_id = row[0]
            await conn.commit()

    logger.info("[Instagram Ingestion] SUCCESS (Fallback): Ingested bookmark placeholder ID=%d for User ID=%d", item_id, user_id)
    logger.info("================================================================================")
    return item_id


def _convert_cookies_json_to_netscape(cookies_json_path: str, netscape_txt_path: str) -> bool:
    """
    Converts a JSON cookie file (Chrome/Firefox export) into Netscape cookie format
    so yt-dlp can consume it. Returns True if file was written successfully.
    """
    import json
    if not os.path.exists(cookies_json_path):
        return False
    try:
        with open(cookies_json_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not isinstance(cookies, list):
            logger.warning("  [Instagram Ingestion] cookies.json is not a valid JSON list — skipping parsing.")
            return False
        with open(netscape_txt_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# Auto-generated from cookies.json\n\n")
            for cookie in cookies:
                if not isinstance(cookie, dict):
                    continue
                domain = cookie.get("domain", "")
                if not domain:
                    continue
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = cookie.get("path", "/")
                secure = "TRUE" if cookie.get("secure", False) else "FALSE"
                expiry = int(cookie.get("expirationDate", 0) or cookie.get("expires", 0) or 0)
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        return True
    except Exception as e:
        logger.error("  [Instagram Ingestion] Failed to convert cookies.json to Netscape: %s", e)
        return False


