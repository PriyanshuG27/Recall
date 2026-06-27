import logging
from datetime import datetime, timezone
import httpx
import psycopg

from backend.config import settings
from backend.services.encryption import decrypt

logger = logging.getLogger(__name__)


class GoogleDocBuilder:
    def __init__(self):
        self.text = ""
        self.requests = []
        self.paragraph_start = 1

    def start_paragraph(self):
        self.paragraph_start = len(self.text) + 1

    def end_paragraph(self, style: str = "NORMAL_TEXT"):
        self.text += "\n"
        paragraph_end = len(self.text) + 1
        self.requests.append({
            "updateParagraphStyle": {
                "range": {
                    "startIndex": self.paragraph_start,
                    "endIndex": paragraph_end
                },
                "paragraphStyle": {
                    "namedStyleType": style
                },
                "fields": "namedStyleType"
            }
        })

    def append_run(self, text: str, bold: bool = False, italic: bool = False):
        start_index = len(self.text) + 1
        self.text += text
        end_index = len(self.text) + 1
        if start_index < end_index and (bold or italic):
            self.requests.append({
                "updateTextStyle": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": end_index
                    },
                    "textStyle": {
                        "bold": bold,
                        "italic": italic
                    },
                    "fields": "bold,italic"
                }
            })


async def _send_telegram_message(chat_id: str, text: str) -> None:
    """
    Sends a message via the Telegram Bot API.
    Redacts the TELEGRAM_BOT_TOKEN in case of exceptions.
    """
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as e:
        err_msg = str(e).replace(settings.TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")
        logger.error("Failed to send Telegram message to chat %s: %s", chat_id, err_msg)


async def sync_user_to_drive(user_id: int, db: psycopg.AsyncConnection) -> None:
    """
    Export a user's 50 most recent items into a Google Docs document stored
    in their Google Drive 'Recall' folder.
    """
    logger.info("Starting Google Docs sync for user %d", user_id)
    
    encrypted_token: str | None = None
    telegram_chat_id: str | None = None
    timezone_offset: int | None = None
    
    # 1. Fetch user data (encrypted refresh token, telegram_chat_id, and timezone_offset)
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT google_refresh_token, telegram_chat_id, timezone_offset FROM users WHERE id = %s;",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            logger.warning("User %d not found in database.", user_id)
            return
        
        encrypted_token, telegram_chat_id, timezone_offset = row
        
    if not encrypted_token:
        logger.info("No Google refresh token connected for user %d. Exiting gracefully.", user_id)
        return

    # Decrypt refresh token in memory
    refresh_token = decrypt(encrypted_token)
    access_token: str | None = None

    try:
        # 2. Exchange refresh token for access token using Google's OAuth token endpoint
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    }
                )
                token_resp.raise_for_status()
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 401:
                    logger.warning("Google refresh token revoked/expired (401) for user %d. Clearing token and notifying.", user_id)
                    # Clear the token in DB
                    async with db.cursor() as cur:
                        await cur.execute(
                            "UPDATE users SET google_refresh_token = NULL WHERE id = %s;",
                            (user_id,)
                        )
                        await db.commit()
                    # Notify the user
                    if telegram_chat_id:
                        msg = "⚠️ Google Drive disconnected! Your access has been revoked or expired. Please reconnect it from the web dashboard."
                        await _send_telegram_message(telegram_chat_id, msg)
                    return
                elif status_code == 403:
                    logger.error("Google API permission/quota error (403) for user %d. Skipping user.", user_id)
                    return
                else:
                    logger.error("HTTP status error exchanging refresh token for user %d: %s", user_id, e.response.text)
                    raise
            
            if not access_token:
                logger.error("Google token response did not contain access_token for user %d", user_id)
                return

            # 3. Retrieve user's 50 most recent items
            items = []
            async with db.cursor() as cur:
                await cur.execute(
                    """
                    SELECT title, summary, source_url, created_at
                    FROM items
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 50;
                    """,
                    (user_id,)
                )
                items = await cur.fetchall()

            # 4. Generate Document in User's Local Time using GoogleDocBuilder
            from datetime import timedelta
            offset_min = timezone_offset or 0
            user_tz = timezone(timedelta(minutes=offset_min))
            
            username = telegram_chat_id or f"user_{user_id}"
            local_now = datetime.now(user_tz)
            date_str = local_now.strftime("%Y-%m-%d")

            builder = GoogleDocBuilder()

            # Document Title
            builder.start_paragraph()
            builder.append_run(f"Recall Export — {username}", bold=True)
            builder.end_paragraph("HEADING_1")

            # Document Meta
            builder.start_paragraph()
            builder.append_run(f"Exported on: {date_str} (Local Time)")
            builder.end_paragraph("NORMAL_TEXT")

            builder.start_paragraph()
            builder.append_run(f"Total items exported: {len(items)}")
            builder.end_paragraph("NORMAL_TEXT")

            builder.start_paragraph()
            builder.append_run("—" * 40)
            builder.end_paragraph("NORMAL_TEXT")

            for item in items:
                title, summary, source_url, created_at = item
                item_title = title or "Untitled Item"
                if created_at:
                    utc_created = created_at.replace(tzinfo=timezone.utc)
                    local_created = utc_created.astimezone(user_tz)
                    created_str = local_created.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created_str = "Unknown Date"
                
                # Item Title
                builder.start_paragraph()
                builder.append_run(item_title, bold=True)
                builder.end_paragraph("HEADING_2")

                # Saved At detail
                builder.start_paragraph()
                builder.append_run("• Saved At: ", bold=True)
                builder.append_run(created_str)
                builder.end_paragraph("NORMAL_TEXT")

                # Source URL detail
                if source_url:
                    builder.start_paragraph()
                    builder.append_run("• Source URL: ", bold=True)
                    builder.append_run(source_url)
                    builder.end_paragraph("NORMAL_TEXT")

                # Summary detail
                if summary:
                    summary_lines = summary.split("\n")
                    for line in summary_lines:
                        line_strip = line.strip()
                        if not line_strip:
                            continue
                        
                        if line_strip.startswith("###"):
                            builder.start_paragraph()
                            builder.append_run(line_strip.lstrip("#").strip(), bold=True)
                            builder.end_paragraph("HEADING_3")
                        elif line_strip.startswith("##"):
                            builder.start_paragraph()
                            builder.append_run(line_strip.lstrip("#").strip(), bold=True)
                            builder.end_paragraph("HEADING_2")
                        elif line_strip.startswith("-"):
                            content = line_strip.lstrip("-").strip()
                            builder.start_paragraph()
                            if content.startswith("**") and "**" in content[2:]:
                                parts = content.split("**", 2)
                                builder.append_run("• " + parts[1] + ": ", bold=True)
                                builder.append_run(parts[2].lstrip(":").strip())
                            else:
                                builder.append_run("• " + content)
                            builder.end_paragraph("NORMAL_TEXT")
                        else:
                            builder.start_paragraph()
                            if line_strip.startswith("**") and line_strip.endswith("**"):
                                builder.append_run(line_strip.replace("**", ""), bold=True)
                            else:
                                builder.append_run(line_strip)
                            builder.end_paragraph("NORMAL_TEXT")

                # Divider
                builder.start_paragraph()
                builder.append_run("—" * 40)
                builder.end_paragraph("NORMAL_TEXT")

            # Headers for Google API calls
            headers = {"Authorization": f"Bearer {access_token}"}

            # 5. Search for 'Recall' folder
            folder_resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": "name = 'Recall' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    "spaces": "drive",
                    "fields": "files(id)"
                },
                headers=headers
            )
            folder_resp.raise_for_status()
            folders = folder_resp.json().get("files", [])
            
            folder_id = None
            if folders:
                folder_id = folders[0]["id"]
                logger.info("Found existing Recall folder with ID %s", folder_id)
            else:
                logger.info("Creating new Recall folder")
                create_folder_resp = await client.post(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "name": "Recall",
                        "mimeType": "application/vnd.google-apps.folder"
                    }
                )
                create_folder_resp.raise_for_status()
                folder_id = create_folder_resp.json().get("id")

            if not folder_id:
                logger.error("Failed to retrieve or create Recall folder ID")
                return

            # 6. Check if daily document already exists
            doc_name = f"Recall — {username} — {date_str}"
            files_resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": f"name = '{doc_name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false",
                    "spaces": "drive",
                    "fields": "files(id)"
                },
                headers=headers
            )
            files_resp.raise_for_status()
            docs = files_resp.json().get("files", [])
            
            document_id = None
            if docs:
                document_id = docs[0]["id"]
                logger.info("Found existing Google Doc with ID %s, updating content", document_id)
            else:
                logger.info("Creating new Google Doc inside folder %s", folder_id)
                create_doc_resp = await client.post(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "name": doc_name,
                        "mimeType": "application/vnd.google-apps.document",
                        "parents": [folder_id]
                    }
                )
                create_doc_resp.raise_for_status()
                document_id = create_doc_resp.json().get("id")

            if not document_id:
                logger.error("Failed to retrieve or create Google Doc ID")
                return

            # 7. Update document content via Google Docs API
            get_doc_resp = await client.get(
                f"https://docs.googleapis.com/v1/documents/{document_id}",
                headers=headers
            )
            try:
                get_doc_resp.raise_for_status()
            except httpx.HTTPStatusError as err:
                logger.error("Docs API HTTPStatusError. Response body: %s", err.response.text)
                raise
            doc_data = get_doc_resp.json()
            
            content_list = doc_data.get("body", {}).get("content", [])
            end_index = content_list[-1].get("endIndex") if content_list else 1

            requests = []
            if end_index > 2:
                requests.append({
                    "deleteContentRange": {
                        "range": {
                            "startIndex": 1,
                            "endIndex": end_index - 1
                        }
                    }
                })
            
            requests.append({
                "insertText": {
                    "location": {
                        "index": 1
                    },
                    "text": builder.text
                }
            })
            
            requests.extend(builder.requests)

            update_resp = await client.post(
                f"https://docs.googleapis.com/v1/documents/{document_id}:batchUpdate",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "requests": requests
                }
            )
            update_resp.raise_for_status()

            # 8. Update google_last_sync in the database
            async with db.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE users
                    SET google_last_sync = CURRENT_TIMESTAMP
                    WHERE id = %s;
                    """,
                    (user_id,)
                )
                await db.commit()
            
            logger.info("Successfully completed Google Docs sync for user %d", user_id)

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 401:
            logger.warning("Google access/refresh token revoked/expired (401) during API call for user %d. Clearing token and notifying.", user_id)
            async with db.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET google_refresh_token = NULL WHERE id = %s;",
                    (user_id,)
                )
                await db.commit()
            if telegram_chat_id:
                msg = "⚠️ Google Drive disconnected! Your access has been revoked or expired. Please reconnect it from the web dashboard."
                await _send_telegram_message(telegram_chat_id, msg)
            return
        elif status_code == 403:
            logger.error("Google API permission/quota error (403) during API call for user %d. Skipping user. Details: %s", user_id, e.response.text)
            return
        else:
            logger.error("HTTP status error during Google Drive sync for user %d: %s", user_id, e.response.text)
            raise
    except Exception as e:
        logger.error("Error during Google Drive sync for user %d: %s", user_id, e, exc_info=True)
        raise
    finally:
        # Secure cleanup: Discard access token and clear local references
        access_token = None
        refresh_token = None
        encrypted_token = None
        headers = None
