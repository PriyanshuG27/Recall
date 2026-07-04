# Mobile Share Sheet Configuration Guide

Recall allows mobile users to instantly save web pages, links, and text directly into their cognitive memory graph using native Share Sheets on iOS and Android.

---

## 📱 1. iOS Shortcuts (Share Sheet) Setup

### Overview
You can create an iOS Shortcut that accepts URLs or text from Safari or any app's Share Sheet and posts them directly to your Recall backend.

### Step-by-Step Instructions:
1. Open the **Shortcuts** app on your iPhone or iPad.
2. Tap **+** to create a new shortcut and name it `Save to Recall`.
3. In the Shortcut Settings (info icon `i`), enable **Show in Share Sheet**.
4. Set **Receives** to `URLs` and `Text`.
5. Add the following action steps:
   - **Get Contents of URL**:
     - **URL**: `https://your-recall-instance.onrender.com/api/ingest`
     - **Method**: `POST`
     - **Headers**:
       - `Authorization`: `Bearer YOUR_JWT_OR_TWA_TOKEN`
       - `Content-Type`: `application/json`
     - **Request Body**: `JSON`
       - `raw_text`: `Shortcut Input`
       - `source_type`: `url`
6. Add action **Show Notification**:
   - **Title**: `Saved to Recall!`
   - **Body**: `Your link has been ingested into your memory graph.`

---

## 🤖 2. Android Share Intent Setup

### Overview
On Android, you can use apps like **HTTP Request Shortcuts** or **Tasker** to capture URLs from the Android Share Menu and send them to Recall.

### HTTP Request Shortcuts Configuration:
- **Shortcut Name**: `Save to Recall`
- **Method**: `POST`
- **URL**: `https://your-recall-instance.onrender.com/api/ingest`
- **Request Body Type**: `JSON`
- **JSON Payload**:
  ```json
  {
    "raw_text": "{share_text}",
    "source_type": "url"
  }
  ```
- **Custom Headers**:
  ```http
  Authorization: Bearer YOUR_JWT_OR_TWA_TOKEN
  Content-Type: application/json
  ```
- **Response Handling**: Show Toast on HTTP 200 (`"Saved to Recall ✓"`).

---

## ⚡ 3. Direct API Endpoints

- **Endpoint**: `POST /api/ingest`
- **Payload Example**:
  ```json
  {
    "raw_text": "https://en.wikipedia.org/wiki/Stoicism",
    "source_type": "url",
    "context_note": "Saved from mobile browser"
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "item_id": 1042,
    "detail": "Item processed and indexed into vector memory graph."
  }
  ```
