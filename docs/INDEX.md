> **Audience**: New Contributors, Maintainers, Reviewers  
> **Estimated Reading Time**: 3 min

# Recall — Official Technical Documentation Index

Welcome to the technical documentation suite for **Recall**, an AI-powered personal knowledge management system and 3D Observatory.

This documentation system is designed according to the **Single Responsibility Principle (SRP)** and grounded strictly in codebase implementation.

---

## 📚 Core Documentation Library

```
                              ┌────────────────────────────────┐
                              │     README.md (Landing Page)   │
                              └───────────────┬────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────┐
                              │    docs/INDEX.md (Doc Hub)     │
                              └───────────────┬────────────────┘
                                              │
     ┌──────────────────┬─────────────────────┼─────────────────────┬──────────────────┐
     │                  │                     │                     │                  │
     ▼                  ▼                     ▼                     ▼                  ▼
┌───────────────┐  ┌───────────┐         ┌───────────┐         ┌───────────┐     ┌───────────┐
│ ARCHITECTURE  │  │ DATABASE  │         │    API    │         │ FEATURES  │     │  TESTING  │
└───────┬───────┘  └───────────┘         └───────────┘         └───────────┘     └───────────┘
        │
        ▼
┌───────────────┐  ┌───────────┐         ┌───────────┐         ┌───────────┐     ┌───────────┐
│   DIAGRAMS    │  │  SECURITY │         │DEVELOPMENT│         │ DEPLOYMENT│     │CONTRIBUTING│
└───────────────┘  └───────────┘         └───────────┘         └───────────┘     └───────────┘
```

---

## 📖 Public Documentation Guides

### 1. System Design & Architecture
* [🚀 System Architecture Guide](ARCHITECTURE.md) — Multi-tier gateway, workers, AI Cascade, queues, and lifecycles.
* [📊 Visual Diagrams Index](DIAGRAMS.md) — Comprehensive visual collection of all 10 verified Mermaid diagrams.
* [📋 Architecture Decision Records (ADRs)](adr/README.md) — Formal records of key architectural decisions.

### 2. Core Technical Specifications
* [🗄️ Database Reference](DATABASE.md) — Neon PostgreSQL schema, 13 tables, HNSW vector search, trigram text search.
* [🔌 API Endpoint Reference](API.md) — Complete reference for all 50 FastAPI REST & WebSocket endpoints.
* [🌟 Feature Specifications Matrix](FEATURES.md) — Categorized matrix of 22 capabilities across production, active dev, partial, and legacy.

### 3. Developer Workflows & Operations
* [🛠️ Development Guide](DEVELOPMENT.md) — Local environment setup, `Makefile` targets, debugging, and new feature workflow.
* [☁️ Deployment Guide](DEPLOYMENT.md) — Hosting setup (Koyeb, Vercel, Azure Student VM) and 28 environment variables.
* [🧪 Testing Framework Guide](TESTING.md) — Test strategy across 151 test files (Pytest, Vitest, Playwright, k6 load scripts).
* [🛡️ Security Architecture](SECURITY.md) — Fernet AES-128 encryption, HMAC verification, httpOnly cookies, PII masking.

### 4. Governance & Contributions
* [🤝 Contributing Guidelines](CONTRIBUTING.md) — Development principles, workspace rules from `AGENTS.md`, and PR checklist.


---

← [README](../README.md) | [Architecture](ARCHITECTURE.md) →

## Related Documentation

[README](../README.md) · **Index** · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [API](API.md) · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
