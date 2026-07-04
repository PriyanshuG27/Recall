# ✦ Recall — AI Knowledge Management & Observatory

> Forward anything to Telegram. Find everything with natural language. Your second brain, connected.

![Recall Observatory 3D Starry Sky](fastapi_flow.png)

---

## ✦ Key Capabilities

- **✦ 3D Observatory Environment**: Starry Sky constellation mind map (`NebulaCanvas.jsx`) rendered with Three.js / React Three Fiber at 60 FPS, alongside a 3D Glass Archive Cylinder (`ArchiveCylinder.jsx`).
- **✦ Interactive RAG Citations**: Clicking citation badges (`[1]`, `[2]`) in AI assistant answers automatically switches to Map (`/map`), smoothly pans and zooms camera transform to center cited node at scale $k = 1.35$, selects the node, highlights connection lines, and animates a 3-second gold flare ring.
- **✦ Multi-Tier Ingestion**: Ingests text, voice audio (Whisper), PDFs (PyPDF chunking & pdfplumber), images (Pillow contrast 2.0x / sharpening + Tesseract OCR), and YouTube/Instagram reels via Cobalt API & OpenGraph HTML scraping fallback.
- **✦ Multi-Tier AI Cascade**: Groq Llama 3 70B ➔ Gemini 1.5 Pro ➔ Modal GPU fallback with dynamic Markdown templates (Variants A-F), brand spelling repair ('TestSprite'), and dead-letter queue recovery.
- **✦ Passive Context & Onboarding**: Passive context tracking (`compute_passive_context`), location-based timezone auto-detection (`round(lon / 15.0 * 2) / 2`), and Day 1-5 onboarding state machine.
- **✦ Active Recall & Spaced Repetition**: SuperMemo SM-2 algorithm quiz generator and drill flashcards (`/drill`).
- **✦ Telegram Friend Fast-Track (`/match`)**: 5-question thought-compatibility game generating referral links (`https://t.me/RecallBot?start=match_{user_id}`) and computing tag synergy scores.
- **✦ Floating PWA Banner**: Dark glassmorphic banner (`PWAInstallBanner.jsx`) with gold 'R' monogram logo, install trigger, and session dismissal.

---

## 🏗 System Architecture

```
Telegram Bot / Chrome Extension / SPA
       │
       ▼
 FastAPI Backend (Port 8000)
       │
 ┌─────┴──────────────────┐
 ▼                        ▼
Upstash Redis Queue   Neon PostgreSQL (pgvector + pg_trgm)
 │                        │
 ▼                        ▼
Worker Ingestion      HNSW Cosine Vector Search (<10ms)
 │
 ▼
AI Cascade (Groq ➔ Gemini ➔ Modal GPU)
```

---

## ⚡ Quick Start

### 1. Backend Setup (FastAPI + Async Worker)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### 2. Frontend Setup (React 18 + Vite SPA)
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testing & Quality Gates

```bash
# Run Backend Pytest Suite (525 Passed, 0 Failed, 62.11% Coverage)
.venv\Scripts\pytest backend/tests/

# Run Frontend Vitest Suite (199 Passed, 0 Failed, 75.26% Coverage)
npm --prefix frontend test

# Run Production Smoke Test Script
python backend/scripts/smoke_test.py --api-url http://localhost:8000 --token <JWT_TOKEN>
```

---

## 📚 Technical Documentation

- 🚀 [Deployment & Environment Guide](file:///d:/Recall/docs/DEPLOYMENT.md)
- 🔄 [CI/CD Pipeline Guide](file:///d:/Recall/docs/CI_CD_PIPELINE_GUIDE.md)
- 🛡️ [Security Scan Report](file:///d:/Recall/docs/SECURITY_SCAN_REPORT.md)
- ⚡ [Performance Benchmarks](file:///d:/Recall/docs/PERFORMANCE_BENCHMARKS.md)
- 📋 [Manual UI Verification Guide](file:///d:/Recall/docs/MANUAL_VERIFICATION_RECALL_EVOLUTION.md)
- 📖 [Master Prompts Playbook](file:///d:/Recall/docs/PROMPTS_TESTING_DEPLOYMENT_UPDATED.md)
