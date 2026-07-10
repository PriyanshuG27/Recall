import time
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from backend.config import settings

logger = logging.getLogger(__name__)

class BaseReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reranks list of documents for the given query. Returns top settings.RERANK_TOP_N documents."""
        pass


class FastEmbedReranker(BaseReranker):
    def __init__(self):
        import threading
        self._model = None
        self._init_lock = threading.Lock()

    def preload(self):
        """Loads and warms up the model synchronously (for startup lifespans)."""
        if self._model is not None:
            return

        model_name = settings.RERANKER_MODEL
        if model_name == "benchmark_pending":
            logger.warning("Reranker model is 'benchmark_pending'. Preloading skipped.")
            return

        logger.info("Preloading FastEmbed TextCrossEncoder model: %s", model_name)
        start_time = time.perf_counter()
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            # Load the model
            self._model = TextCrossEncoder(model_name=model_name)
            load_time = time.perf_counter() - start_time
            logger.info("Successfully loaded reranker model in %.4f seconds.", load_time)

            # Warmup: Run a dummy prediction to compile/cache ONNX kernels
            warmup_start = time.perf_counter()
            list(self._model.rerank("warmup", ["dummy passage"]))
            warmup_time = time.perf_counter() - warmup_start
            logger.info("Reranker warmup completed in %.4f seconds.", warmup_time)
        except Exception as e:
            logger.error("Failed to preload or warm up reranker model %s: %s", model_name, e)

    def _get_model(self):
        """Lazy loader for fallback or test environments where preload wasn't triggered."""
        if self._model is not None:
            return self._model

        with self._init_lock:
            if self._model is None:
                model_name = settings.RERANKER_MODEL
                if model_name == "benchmark_pending":
                    raise ValueError("Reranker model is 'benchmark_pending' and cannot be initialized.")

                from fastembed.rerank.cross_encoder import TextCrossEncoder
                self._model = TextCrossEncoder(model_name=model_name)
        return self._model

    def _select_passage(self, doc: Dict[str, Any]) -> str:
        """Selects the text representation to feed into the cross-encoder based on hierarchy."""
        # 1. Matched chunk text (highest precision)
        if "matched_chunk_text" in doc and doc["matched_chunk_text"]:
            return str(doc["matched_chunk_text"])
        if "chunk_text" in doc and doc["chunk_text"]:
            return str(doc["chunk_text"])

        # 2. Searchable text
        if "searchable_text" in doc and doc["searchable_text"]:
            return str(doc["searchable_text"])

        # 3. Summary + Title
        summary = doc.get("summary") or ""
        title = doc.get("title") or ""
        if summary or title:
            return f"{title} {summary}".strip()

        # 4. Decrypted raw text fallback
        raw_text = doc.get("raw_text")
        if raw_text:
            try:
                from backend.services.encryption import decrypt
                return decrypt(raw_text)
            except Exception:
                pass

        return ""

    async def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not documents:
            return []

        if not settings.ENABLE_RERANKING or settings.RERANKER_MODEL == "benchmark_pending":
            return documents[:settings.RERANK_TOP_N]

        start_time = time.perf_counter()
        try:
            passages = [self._select_passage(doc) for doc in documents]
            provider = getattr(settings, "RERANKER_PROVIDER", "local")
            if provider == "remote":
                try:
                    from backend.services.remote_ai_client import generate_remote_rerank
                    scores = await generate_remote_rerank(query, passages)
                except Exception as e:
                    logger.error("Remote reranking failed: %s. Falling back to local reranker.", e)
                    provider = "local"
            
            if provider == "local":
                model = await asyncio.to_thread(self._get_model)
                # Run local ONNX cross-encoder model inside a thread executor to keep event loop unblocked
                # Wrapped in a strict timeout boundary
                scores_iterable = await asyncio.wait_for(
                    asyncio.to_thread(lambda: list(model.rerank(query, passages))),
                    timeout=settings.RERANK_TIMEOUT_SECONDS
                )
                scores = list(scores_iterable)

            # Zip and associate scores with documents
            scored_docs = []
            for doc, score in zip(documents, scores):
                # Update score inside document metadata
                doc_copy = doc.copy()
                doc_copy["rerank_score"] = float(score)
                scored_docs.append(doc_copy)

            # Sort descending by rerank score
            scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
            
            latency = time.perf_counter() - start_time
            logger.info(
                "Rerank succeeded. Candidates: %d | Latency: %.4f s | Scores: %s",
                len(documents), latency, [round(d["rerank_score"], 2) for d in scored_docs[:3]]
            )
            return scored_docs[:settings.RERANK_TOP_N]

        except asyncio.TimeoutError:
            logger.warning("Rerank timed out after %.2f seconds. Falling back to original RRF ranks.", settings.RERANK_TIMEOUT_SECONDS)
        except Exception as e:
            logger.error("Rerank encountered error: %s. Falling back to original RRF ranks.", e)

        # Fallback to original database RRF ranks
        return documents[:settings.RERANK_TOP_N]


# Singleton instance container
reranker_service = FastEmbedReranker()
