import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Optional, Dict, Any
import psycopg
import backend.db.connection as db_conn

logger = logging.getLogger(__name__)

# ==============================================================================
# CONTEXT VARIABLES FOR TELEMETRY
# ==============================================================================
# These context vars allow non-intrusive metadata passing down the call chain
current_user_id_var: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)
current_chat_id_var: ContextVar[Optional[str]] = ContextVar("current_chat_id", default=None)
current_task_var: ContextVar[Optional[str]] = ContextVar("current_task", default=None)
current_request_id_var: ContextVar[Optional[str]] = ContextVar("current_request_id", default=None)

@asynccontextmanager
async def cost_tracking_context(
    chat_id: Optional[str] = None,
    user_id: Optional[int] = None,
    task: Optional[str] = None,
    request_id: Optional[str] = None
):
    """
    Async context manager to bind telemetry metadata to the current coroutine context.
    Usage:
        async with cost_tracking_context(chat_id="123456", task="summarise"):
            await cascade.summarise(text)
    """
    token_user_id = current_user_id_var.set(user_id)
    token_chat_id = current_chat_id_var.set(chat_id)
    token_task = current_task_var.set(task)
    token_request_id = current_request_id_var.set(request_id)
    try:
        yield
    finally:
        current_user_id_var.reset(token_user_id)
        current_chat_id_var.reset(token_chat_id)
        current_task_var.reset(token_task)
        current_request_id_var.reset(token_request_id)

# ==============================================================================
# PRICING REGISTRY
# ==============================================================================
# Rates in USD. Tokens are priced per 1,000,000. Audio is priced per minute.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Gemini Models
    "gemini-3.1-flash-lite": {
        "input_cost_per_1m": 0.075,
        "output_cost_per_1m": 0.30,
    },
    
    # Groq Models
    "openai/gpt-oss-120b": {
        "input_cost_per_1m": 0.35,
        "output_cost_per_1m": 0.80,
    },
    "openai/gpt-oss-20b": {
        "input_cost_per_1m": 0.15,
        "output_cost_per_1m": 0.15,
    },
    "qwen/qwen3-32b": {
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 0.20,
    },
    "whisper-large-v3-turbo": {
        "cost_per_minute": 0.0010,
    },
    "whisper-large-v3": {
        "cost_per_minute": 0.0010,
    },
    
    # OpenRouter
    "openai/gpt-oss-120b:free": {
        "input_cost_per_1m": 0.0,
        "output_cost_per_1m": 0.0,
    },
    "meta-llama/llama-3.3-70b-instruct:free": {
        "input_cost_per_1m": 0.0,
        "output_cost_per_1m": 0.0,
    },
    "mistralai/mistral-7b-instruct:free": {
        "input_cost_per_1m": 0.0,
        "output_cost_per_1m": 0.0,
    },
    
    # Nvidia NIM
    "meta/llama3-70b-instruct": {
        "input_cost_per_1m": 0.70,
        "output_cost_per_1m": 0.90,
    },
    "qwen/qwen3-next-80b-a3b": {
        "input_cost_per_1m": 0.70,
        "output_cost_per_1m": 0.90,
    },
    "deepseek/deepseek-v4-pro": {
        "input_cost_per_1m": 0.70,
        "output_cost_per_1m": 0.90,
    },
    "nvidia/gpt-oss-120b": {
        "input_cost_per_1m": 0.70,
        "output_cost_per_1m": 0.90,
    },
    
    # Modal (Custom Serverless Deployments - flat rate approximations)
    "modal-summary": {
        "flat_cost": 0.00010,
    },
    "modal-transcribe": {
        "flat_cost": 0.00020,
    },
    "modal-tags": {
        "flat_cost": 0.00005,
    },
    "modal-rag": {
        "flat_cost": 0.00010,
    },
    
    # Cerebras
    "cerebras/openai/gpt-oss-120b": {
        "input_cost_per_1m": 0.35,
        "output_cost_per_1m": 0.80,
    }
}

DEFAULT_MODEL = "gemini-3.1-flash-lite"

class CostManager:
    @staticmethod
    def estimate_tokens(text: Optional[str]) -> int:
        """
        Fallback token estimator if LLM provider response doesn't contain usage information.
        Approximates ~4 characters per English token.
        """
        if not text:
            return 0
        return max(1, int(len(text) / 4.0))

    @staticmethod
    def calculate_cost(
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_seconds: float = 0.0
    ) -> float:
        """
        Look up pricing rates and calculate the total USD execution cost.
        """
        # Lowercase / normalize the keys
        provider_lower = provider.lower().strip()
        model_name = model.strip() if model else ""
        
        # Check flat rate or special mapping for Modal
        if provider_lower == "modal":
            # Map modal tasks to distinct models if passed as model name
            modal_key = f"modal-{model_name}" if not model_name.startswith("modal-") else model_name
            pricing = MODEL_PRICING.get(modal_key, MODEL_PRICING["modal-summary"])
            return pricing.get("flat_cost", 0.0)

        # Look up model pricing
        pricing = MODEL_PRICING.get(model_name)
        if not pricing:
            # Check prefix/substring matching or fall back
            matched_key = None
            for key in MODEL_PRICING:
                if key in model_name or model_name in key:
                    matched_key = key
                    break
            pricing = MODEL_PRICING.get(matched_key) if matched_key else MODEL_PRICING.get(DEFAULT_MODEL)

        if not pricing:
            logger.warning("No pricing found for model '%s'. Defaulting to 0.0.", model_name)
            return 0.0

        # Case 1: Audio pricing (e.g. Whisper)
        if "cost_per_minute" in pricing:
            minutes = duration_seconds / 60.0
            return round(minutes * pricing["cost_per_minute"], 8)

        # Case 2: Token pricing
        input_rate = pricing.get("input_cost_per_1m", 0.0)
        output_rate = pricing.get("output_cost_per_1m", 0.0)
        
        input_cost = (prompt_tokens / 1_000_000.0) * input_rate
        output_cost = (completion_tokens / 1_000_000.0) * output_rate
        
        return round(input_cost + output_cost, 8)

    @classmethod
    async def log_usage(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_seconds: float = 0.0,
        cursor: Optional[psycopg.AsyncCursor] = None
    ) -> float:
        """
        Calculates the execution cost and logs the usage telemetry to the database.
        Fails safely without raising exceptions to prevent LLM service disruption.
        """
        # 1. Fetch telemetry context from context variables
        user_id = current_user_id_var.get()
        chat_id = current_chat_id_var.get()
        task = current_task_var.get() or "unknown"
        request_id = current_request_id_var.get()

        # 2. Calculate execution cost
        cost = cls.calculate_cost(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_seconds=duration_seconds
        )

        # 3. Log to database
        try:
            # Helper logic to perform DB operation with or without an active cursor
            if cursor:
                await cls._write_log(
                    cursor=cursor,
                    user_id=user_id,
                    chat_id=chat_id,
                    request_id=request_id,
                    provider=provider,
                    model=model,
                    task=task,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_seconds=duration_seconds,
                    cost=cost
                )
            else:
                # Borrow connection from the singleton pool
                if not db_conn._pool:
                    logger.warning("Database connection pool is uninitialized. Telemetry cost logged to stdout: Provider=%s Model=%s Cost=%s", provider, model, cost)
                    return cost
                
                async with db_conn._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cls._write_log(
                            cursor=cur,
                            user_id=user_id,
                            chat_id=chat_id,
                            request_id=request_id,
                            provider=provider,
                            model=model,
                            task=task,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            duration_seconds=duration_seconds,
                            cost=cost
                        )
                        await conn.commit()
        except Exception as e:
            # CRITICAL RULE: Telemetry failure must never disrupt core AI functionality
            logger.error("Failed to log LLM token usage/cost telemetry: %s", e, exc_info=True)

        return cost

    @classmethod
    async def _write_log(
        cls,
        cursor: psycopg.AsyncCursor,
        user_id: Optional[int],
        chat_id: Optional[str],
        request_id: Optional[str],
        provider: str,
        model: str,
        task: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_seconds: float,
        cost: float
    ) -> None:
        """Helper function to perform database resolution and log insert."""
        # Resolve user_id from chat_id if user_id is not set
        if not user_id and chat_id:
            await cursor.execute(
                "SELECT id FROM users WHERE telegram_chat_id = %s LIMIT 1;",
                (str(chat_id),)
            )
            row = await cursor.fetchone()
            if row:
                user_id = row[0]

        total_tokens = prompt_tokens + completion_tokens

        # Insert telemetry log using parameterized query
        await cursor.execute(
            """
            INSERT INTO telemetry_cost_logs (
                user_id,
                request_id,
                provider,
                model,
                task,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                audio_duration_seconds,
                cost_usd
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                user_id,
                request_id,
                provider,
                model,
                task,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                duration_seconds,
                cost
            )
        )
