# ==============================================================================
# RECALL - DEVELOPMENT MAKEFILE
# ==============================================================================
# Shortcuts for common local development tasks.
# On Windows, you can use these commands directly or run them via make/wsl if installed.
# ==============================================================================

.PHONY: dev-backend dev-frontend test tunnel schema fernet jwt-secret help

help:
	@echo "Available commands:"
	@echo "  make dev-backend  - Start the FastAPI backend with hot-reload"
	@echo "  make dev-frontend - Start the React+Vite frontend development server"
	@echo "  make test         - Run backend unit tests using pytest"
	@echo "  make tunnel       - Start an ngrok tunnel on port 8000 (Telegram webhook testing)"
	@echo "  make schema       - Initialize Neon/PostgreSQL database schema"
	@echo "  make fernet       - Generate a secure Fernet key for cryptography"
	@echo "  make jwt-secret   - Generate a secure JWT secret key"

dev-backend:
	cd backend && uvicorn main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -x -v

tunnel:
	ngrok http 8000

schema:
	python -c "import asyncio; from backend.db.connection import init_schema; asyncio.run(init_schema())"

fernet:
	python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

jwt-secret:
	python -c "import secrets; print(secrets.token_hex(32))"
