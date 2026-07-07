# Recall Master Context

## Project intent
Recall is an AI-first personal knowledge operating system. It is designed to become a user's second brain rather than a simple summarizer.

## Scope of this doc set
These documents capture the decisions and plans discussed in this chat only:
- architecture direction
- library adoption
- production hardening
- logging
- analytics
- security and privacy
- retrieval and graph direction
- memory direction
- versioned roadmap

## Hard constraints
- Do not redesign the AI provider cascade.
- Treat the cascade as a black box boundary.
- Keep the FastAPI + PostgreSQL core.
- Avoid framework-first architecture.
- Prefer practical improvements over theoretical completeness.
- Avoid adding multiple tools for the same job.

## Immediate priorities
1. Integrate the branching PoC.
2. Stabilize the new AI cascade interface.
3. Harden security and privacy.
4. Improve logging.
5. Add lightweight V1 analytics.
6. Clean up the codebase.
7. Test the failure paths.
8. Deploy a stable production build.

## Core architectural principle
Recall should own the knowledge model. External libraries may help in narrow slots, but they should not define the product identity.

## Version mindset
- v1: ship the stable core
- v1.1: stabilize from real usage
- v1.2: improve ingestion and structure extraction
- v1.3: improve retrieval quality
- v2: add typed memory and deeper graph intelligence
- v3: scale or specialize infrastructure only if needed

## Working definition of success
A good Recall system should:
- accept many content types safely
- normalize them into one internal format
- retrieve the right context reliably
- remember useful facts correctly
- expose graph relationships naturally
- remain debuggable and measurable
- stay maintainable over time
