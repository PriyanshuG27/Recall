# Atrium — Compliance, Privacy, & App Store Publishing Guide

This guide details the compliance policies, legal templates, and app store validation workflows required to operate Atrium's multi-tenant bot, web app, and browser extension ecosystem.

---

## 1. Privacy Policy Template (Draft)

### 1.1 Data Collection & Ingestion
We collect information that you explicitly submit to the Atrium Platform via our Telegram Bot, Chrome Extension, and Web App:
*   **Media and Files**: Images (screenshots, photos), voice notes (memos, audio clips), and documents (PDFs) uploaded for text extraction and indexing.
*   **Web Content**: URLs, page titles, and body texts clipped via the Browser Extension.
*   **Metadata**: Geolocation and time of day bucket classifications used strictly to build contextual memories.

### 1.2 Data Storage & Cryptographic Security
Atrium treats your personal content with zero-trust storage principles:
*   **At-Rest Encryption**: All raw texts and third-party credentials (like Google OAuth refresh tokens) are encrypted before database persistence using AES-256 standard symmetric cryptography (**Fernet keys**).
*   **Database Host Insulation**: The database hosts (Neon PostgreSQL) and caching layers (Upstash Redis) see only ciphertexts and key-hashes, mitigating data leak impacts.

### 1.3 Downstream AI Processing
To generate vector embeddings, tag networks, and summarizations, we route your processed text to external AI services:
*   **AI Providers**: Google Gemini API, Groq API, and NVIDIA NIM.
*   **Training Disclosures**: Atrium operates on the Google AI Studio Free Tier. Under these terms, Google collects, retains, and utilizes prompts and transcripts to train Google models. Users must not ingest highly sensitive, proprietary, or regulated personal data on the Platform. We do not sell or lease your raw data to any advertising platforms.

### 1.4 Data Deletion & Portability (GDPR / CCPA)
You have full ownership of your data:
*   **Account Deletion**: You can purge your account and delete all associated records cascadingly from the Web UI dashboard settings (`DELETE /api/me`).
*   **Data Portability**: You can export your items as structured JSON (`GET /api/export`) or as a zipped Obsidian Vault (`GET /api/export/zip`) directly from the Web UI.

---

## 2. Terms of Service (ToS) Template (Draft)

### 2.1 Intellectual Property
*   **User Ownership**: You retain full ownership, copyrights, and intellectual property rights for any content (notes, links, documents) you upload to Atrium.
*   **Atrium License**: You grant Atrium a narrow, secure license solely to process and encrypt your content to display your mind map and generate reviews.

### 2.2 Downstream AI Disclaimer
*   Atrium utilizes advanced Large Language Models (LLMs) to summarize and tag items. You acknowledge that AI outputs can contain errors, inaccuracies, or "hallucinations." Atrium is not liable for actions taken based on AI-generated summaries.

### 2.3 Account Suspension & Abuse
*   We reserve the right to suspend accounts attempting to prompt-inject our AI gateway, bypass rate limiters, or run denial-of-service scripts against our endpoints.

---

## 3. Chrome Web Store MV3 Publishing Guidelines

To publish the Chrome Extension ([frontend/extension](file:///d:/Recall/frontend/extension/)) with automated store approval (bypassing broad-permission audits):

### 3.1 Narrowing `host_permissions`
Do **not** request `<all_urls>` in production. Limit the scope to your exact server domain:
```json
  "host_permissions": [
    "https://*.yourdomain.com/*"
  ]
```
This satisfies the Chrome Web Store's *Principle of Least Privilege* and allows access to the `jwt` authentication cookie on your domain without requiring manual security reviews.

### 3.2 MV3 Content Security Policy (CSP)
*   **No Remote Code**: Do not include script tags loading external CDNs (like jQuery or Google Analytics). All assets must be bundled inside the extension package.
*   **No Dynamic Code**: Do not use `eval()` or `new Function()` in extension JS utilities.

---

## 4. Google OAuth Verification Steps

Since Atrium requests access to create and manage backup files in Google Drive (`drive.file` scope), Google Cloud Console requires application verification.

### 4.1 Prerequisites
1.  **Public Website**: Host your Privacy Policy and Terms of Service publicly on your domain (e.g., `https://yourdomain.com/privacy`).
2.  **DNS Verification**: Verify ownership of the domain in Google Search Console.

### 4.2 Consent Screen Setup
*   Configure the OAuth Consent Screen in Google Cloud Console.
*   Specify the scopes: `https://www.googleapis.com/auth/drive.file` (broad scopes like `drive.readonly` or `drive` are **Restricted Scopes** and require a costly, complex third-party security audit; avoid them).

### 4.3 Demo Video Guidelines (Required)
You must submit a YouTube video demonstration showing:
1.  The user's perspective logging into the Atrium Web UI.
2.  Clicking the "Connect Google Drive" button.
3.  The Google OAuth authentication window showing your app name and client ID in the URL.
4.  Grants confirmation showing `drive.file` consent.
5.  How the app writes to Google Drive, and how the user can revoke the connection.
