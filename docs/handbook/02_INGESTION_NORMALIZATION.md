# Chapter 2: Ingestion, Normalization & Document Understanding

## 1. Introduction
Ingestion is the entry point for all knowledge entering Recall. The system must not merely store files; it must understand them deeply enough to extract durable knowledge. This chapter defines the ingestion pipeline responsible for verifying, parsing, and normalizing diverse data sources (PDFs, images, voice notes, web links, raw text) into a unified internal representation, preserving structural cues like headings, tables, and relationships.

## 2. Current Recall implementation
Recall currently features a multi-modal ingestion pipeline. Incoming payloads (from Telegram, Web, or the Chrome extension) are categorized by `source_type`. Simple text and links are processed via HTTP fetching and raw extraction. Images undergo OCR, and audio notes utilize transcription services (e.g., Whisper). Output text is segmented and passed to the AI Cascade for summarization, entity extraction, and vector embedding. 

## 3. Problems
*   **Premature Flattening:** A naive chunking approach flattens complex documents early in the pipeline, destroying layout structures (headings, tables, footnotes).
*   **Format Brittle Logic:** Custom parsers for PDFs or HTML are brittle and require constant maintenance.
*   **Missing Normalization Layer:** The system lacks a strictly enforced "Normalized Document" schema, meaning downstream processors handle slightly different data shapes depending on the original source type.
*   **Security Gaps:** Lack of comprehensive zip/archive bomb detection or deep malformed input validation before parsing.

## 4. Design Goals
*   **Universal Internal Representation:** Every input type must converge into a single, structured internal document model before chunking.
*   **Structure Preservation:** Preserve document hierarchy (sections, paragraphs, lists, tables).
*   **Robust Parsing via Abstraction:** Offload messy format-specific parsing to dedicated libraries (like `unstructured`) where appropriate.
*   **Secure Ingestion:** Validate file sizes, types, and detect decompression bombs immediately.

## 5. Architecture
The ingestion pipeline is designed as a linear sequence:
1.  **Validation Layer:** MIME type checking, size limits, safety scans.
2.  **Parser/Adapter Layer:** Routes documents to the correct parser (OCR, ASR, HTML scraper, PDF layout analyzer).
3.  **Normalization Layer:** Maps parsed results to the internal `Document` schema.
4.  **Enrichment Layer:** AI Cascade performs entity/metadata extraction.
5.  **Chunking Layer:** Semantic and structural chunking prepares the normalized document for vector storage.

## 6. Data Flow
1.  Payload arrives (e.g., `invoice.pdf` via Telegram).
2.  Validation rejects if `> 50MB` or malformed.
3.  The payload routes to the PDF Parser (utilizing library support for layout analysis).
4.  The Parser returns raw layout elements (Title, Text, Table).
5.  The Normalization layer maps these elements into a standard JSON `Document`.
6.  The Chunking layer divides the document intelligently (e.g., keeping tables intact, splitting sections).
7.  The enriched document and its chunks are inserted into the PostgreSQL `items` and `item_chunks` tables.

## 7. Diagrams

```mermaid
flowchart LR
    A[Source File] --> B[Validation]
    B --> C{Router}
    C -- PDF/DOCX --> D1[Layout Parser (Unstructured)]
    C -- Image --> D2[OCR Engine]
    C -- Audio --> D3[ASR Transcription]
    C -- Text --> D4[Text Extractor]
    
    D1 & D2 & D3 & D4 --> E[Normalized Document Model]
    E --> F[Semantic & Structural Chunking]
    E --> G[Metadata/Entity Extraction]
    F & G --> H[(PostgreSQL)]
```

## 8. Interfaces
*   **Normalized Document Schema:**
    ```json
    {
      "source_type": "pdf",
      "title": "Quarterly Report",
      "metadata": { "sensitivity": "high", "provenance": "telegram" },
      "elements": [
        { "type": "heading", "content": "Q3 Results", "level": 1 },
        { "type": "paragraph", "content": "Revenue grew by 5%..." }
      ]
    }
    ```

## 9. Database Changes
*   `items.passive_context` JSONB column stores provenance and validation metadata.
*   `item_chunks` handles large document splits. The `cascade_delete_item_chunks` trigger ensures orphaned chunks are deleted when an item is purged.

## 10. Folder Structure
*   `backend/services/ingestion/`: New directory for ingestion adapters.
*   `backend/services/ingestion/validators/`: File safety checks.
*   `backend/services/ingestion/parsers/`: Adapters for Unstructured, Whisper, Tesseract.
*   `backend/services/ingestion/normalizers/`: Mappers to the internal schema.

## 11. API Changes
*   `/api/upload`: New universal upload endpoint supporting multipart forms, returning a polling `job_id` instead of blocking for parsing.

## 12. Migration Strategy
1.  Introduce the `Document` internal schema alongside existing direct-to-text flows.
2.  Route simple text through the new normalizer to verify pipeline integrity.
3.  Integrate the `unstructured` library for PDFs and HTML, replacing custom scraping glue.
4.  Deprecate old format-specific processing functions.

## 13. Rollback Strategy
Maintain legacy text-extraction functions in `legacy/adapters.py`. If the new parser crashes or OOMs on complex PDFs, a feature flag can revert the PDF processing to basic text extraction (ignoring layout).

## 14. Performance
*   **Memory Footprint:** Parsing large PDFs with layout analysis is memory-intensive. Workers executing PDF parsing must be isolated or bounded by strict memory limits.
*   **Latency:** Audio and PDF ingestion are entirely asynchronous. Target chunking time: `< 2 seconds` per MB.

## 15. Failure Modes
*   **Parser Timeout:** Complex PDFs or massive tables can stall layout analysis. Implement strict 30-second parsing timeouts.
*   **Corrupt Files:** Fails safely at the Validation layer; logs `PARSE_FAILED` and pushes to the `dead_letter_queue`.
*   **Unrecognized Format:** Falls back to binary storage with a "Needs Manual Review" flag if the user forced the upload.

## 16. Security Considerations
*   **File Upload Vulnerabilities:** Prevent SSRF from link ingestion, ZIP bombs from archives, and malicious SVG executions.
*   **Sensitivity Classification:** Pre-parsing classification should flag PII. Highly sensitive documents might bypass external AI providers and run strictly on local fallback models.

## 17. Complexity Analysis
*   **Time Complexity:** O(N) where N is the number of pages/tokens in the document.
*   **Space Complexity:** O(N) in memory during layout analysis before being garbage collected post-serialization.

## 18. Tradeoffs
*   **Layout Parsing vs. Speed:** Analyzing a PDF for tables and headings is significantly slower than naive PyPDF text extraction. We trade ingestion speed for massive downstream retrieval and RAG quality improvements.

## 19. Alternatives Considered
*   **Custom Regex Scrapers:** Rejected. Too brittle across millions of edge cases on the internet.
*   **LlamaIndex Native Readers:** Rejected for core ingestion. Recall requires a proprietary internal `Document` schema, not a framework-coupled object. 

## 20. Final Recommendation
Adopt the `unstructured` library for heavy-lifting format parsing (PDFs, DOCX). Enforce the `Normalized Document` JSON schema as the absolute boundary between parsing and AI processing.

## 21. Implementation Checklist
*   [ ] Define the Pydantic `NormalizedDocument` schema.
*   [ ] Implement a unified MIME/Size validator interceptor.
*   [ ] Integrate `unstructured` for PDF layout extraction.
*   [ ] Refactor text/URL ingest to map to the new schema before chunking.

## 22. Future Improvements
*   Local fast-path heuristics to bypass deep parsing for trivially simple documents.
*   Image-based table understanding using vision models prior to text extraction.

## 23. Version
1.0.0

## 24. Priority
P1 - High (Blocks advanced RAG capabilities)

## 25. Estimated Engineering Effort
5 Developer Days.
