# Observability and Evaluation

## Why this matters
A knowledge system without evaluation will drift. If Recall cannot measure its own retrieval, parsing, and AI quality, then improvements will be guesswork.

## What to measure
### Retrieval quality
- success rate
- zero-result rate
- reranker gain
- hit quality
- graph vs vector candidate usefulness

### AI quality
- fallback rate
- parse success rate
- hallucination reports
- answer acceptance
- regeneration rate

### Ingestion quality
- parse failures
- OCR failures
- transcription failures
- layout extraction quality

### System quality
- latency
- retries
- worker failure rate
- queue depth

## What tools are worth adding
- Sentry for error visibility
- structlog for structured events
- optionally Promptfoo, Ragas, Phoenix, or Langfuse later when evaluation sets exist

## Evaluation philosophy
Do not optimize prompts or retrieval without a benchmark set. Build small evaluation collections of:
- good searches
- bad searches
- useful answers
- failed answers
- tricky documents
- high-risk documents

## What good looks like
A change to chunking, ranking, or prompts should produce a measurable delta.
