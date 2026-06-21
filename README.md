# Recall — Telegram-first AI Knowledge Mind Map

Recall is a Telegram-first knowledge management bot with an interactive constellation mind map dashboard.

## Overview
- **Frictionless Ingestion**: Forward any link, voice note, PDF, or image to the Telegram Bot.
- **AI Processing**: Whispers audio, extracts metadata, summarizes content, generates embeddings, and schedules spaced-repetition quizzes.
- **Visual Mind Map**: Render orbital and community nodes in real-time on a HTML5 Canvas.

## Setup & Deployment Instructions
Please refer to the detailed deployment documentation located at:
- [docs/DEPLOYMENT.md](file:///d:/Recall/docs/DEPLOYMENT.md) for environment configuration, database setup, locally running the servers, and deploying to Vercel/Render.

## Project Structure
- `backend/`: FastAPI API endpoint, database schema, seeder scripts, tests, and task worker queues.
- `frontend/`: React + Vite SPA, canvas mind map renderer, login page, settings, and components.
- `docs/`: Product briefs, technical plans, and API blueprints. 
