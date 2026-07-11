"""
backend/services/ocr_service.py
===============================
Enhanced local OCR service wrapper utilizing PIL image preprocessing,
OpenCV QR code detection, and in-memory local PaddleOCR with confidence filtering.
Runs PaddleOCR inside a ProcessPoolExecutor so that C++ GIL-blocking compilation
cannot freeze uvicorn worker threads. The OCR subprocess singleton persists for
the lifetime of the worker process, so cold-start only occurs once.
"""

import io
import os
import logging
import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Union, Optional
from PIL import Image
from backend.config import settings

# Set env vars before any paddle import (must be done at module level in
# the *worker* process — these are inherited when the pool is forked/spawned).
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

logger = logging.getLogger(__name__)

# ProcessPoolExecutor with a single worker so PaddleOCR runs in an isolated
# subprocess and cannot block uvicorn's event loop or thread pool.
_ocr_executor: Optional[ProcessPoolExecutor] = None

# Module-level singleton inside the *worker* subprocess (not the uvicorn process).
_paddle_client = None

def check_paddleocr_available() -> bool:
    """Check if paddleocr and paddlepaddle are installed and available without importing them."""
    import importlib.util
    try:
        paddleocr_spec = importlib.util.find_spec("paddleocr")
        paddle_spec = importlib.util.find_spec("paddle")
        return paddleocr_spec is not None and paddle_spec is not None
    except Exception:
        return False

def get_paddle_client():
    """Retrieves the cached singleton PaddleOCR client (runs inside subprocess)."""
    global _paddle_client
    if _paddle_client is None:
        if not check_paddleocr_available():
            raise RuntimeError("PaddleOCR or PaddlePaddle is not installed/available.")
        from paddleocr import PaddleOCR
        # Disable document-level preprocessing (UVDoc unwarping, doc orientation,
        # textline orientation) — these are designed for scanned paper docs and
        # actively degrade screenshot / social-media image OCR.
        # Only the core detect+recognise pipeline is needed for UI screenshots.
        for kwargs in [
            # 1. New version settings (disable document / orientation stages)
            dict(
                lang="en",
                show_log=False,
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            ),
            # 2. Older version settings (disable angle classification)
            dict(
                lang="en",
                show_log=False,
                use_angle_cls=False,
            ),
            # 3. Bare minimum fallback
            dict(lang="en"),
        ]:
            try:
                _paddle_client = PaddleOCR(**kwargs)
                break
            except Exception:
                continue
        if _paddle_client is None:
            raise RuntimeError("Failed to initialise PaddleOCR with any known parameter set.")
    return _paddle_client

def _get_ocr_executor() -> ProcessPoolExecutor:
    """Returns the module-level ProcessPoolExecutor, creating it if needed."""
    global _ocr_executor
    if _ocr_executor is None:
        import os
        is_prod = os.environ.get("ENV") == "production"
        max_workers = 2 if is_prod else 1
        _ocr_executor = ProcessPoolExecutor(max_workers=max_workers)
    return _ocr_executor

def preprocess_and_ocr_image(image_bytes: bytes) -> dict:
    """
    Performs QR code detection and PaddleOCR on image bytes.
    Runs entirely in memory. Preprocessing is intentionally minimal:
    PP-OCRv5 is a neural network that performs its own internal preprocessing
    — aggressive binarization or contrast enhancement destroys the features
    it relies on and results in 0 characters extracted.
    """
    import numpy as np
    import cv2
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as img_err:
        logger.error("Failed to open image bytes in OCR preprocessing: %s", img_err)
        return {"ocr_text": None, "trigger_gemini_fallback": True}

    # Convert to RGB numpy array (consistent colour space for all inputs)
    if image.mode != "RGB":
        image = image.convert("RGB")
    img_np = np.array(image)

    # 1. Detect QR code URL on the original image
    qr_url = None
    try:
        bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(bgr)
        if data and data.strip().lower().startswith(("http://", "https://", "www.")):
            qr_url = data.strip()
            logger.info("Successfully extracted QR code URL: %s", qr_url)
    except Exception as qr_err:
        logger.warning("In-memory QR code detection failed: %s", qr_err)

    # 2. Minimal preprocessing — upscale only if image is very small.
    #    PP-OCRv5 handles contrast, noise, and binarization internally.
    h, w = img_np.shape[:2]
    if w < 640:
        scale = 1280.0 / w
        img_np = cv2.resize(img_np, (1280, int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # Convert RGB → BGR for OpenCV/PaddleOCR
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    high_conf_words = []
    try:
        ocr_client = get_paddle_client()
        result = ocr_client.ocr(img_bgr)

        if isinstance(result, list) and len(result) > 0 and result[0]:
            first_res = result[0]
            if isinstance(first_res, dict):
                # PaddleX / PP-Structure output format
                rec_texts = first_res.get("rec_texts", [])
                rec_scores = first_res.get("rec_scores", [])
                for text, conf in zip(rec_texts, rec_scores):
                    if isinstance(text, str) and isinstance(conf, (int, float)):
                        if conf >= 0.60 and text.strip():
                            high_conf_words.extend(text.strip().split())
            else:
                # Standard PaddleOCR nested list output format
                for line in first_res:
                    if isinstance(line, (list, tuple)) and len(line) > 1:
                        info = line[1]
                        if isinstance(info, (list, tuple)) and len(info) > 1:
                            text = info[0]
                            conf = info[1]
                            if isinstance(text, str) and isinstance(conf, (int, float)):
                                if conf >= 0.60 and text.strip():
                                    high_conf_words.extend(text.strip().split())
    except Exception as ocr_err:
        logger.error("In-memory PaddleOCR execution failed: %s", ocr_err)

    ocr_result_text = " ".join(high_conf_words)

    # Append QR code URL to OCR text if found
    if qr_url:
        ocr_result_text = (ocr_result_text + "\n" + qr_url).strip() if ocr_result_text else qr_url

    # 4. Fallback trigger check (fewer than 10 words and no QR URL)
    total_words = len(ocr_result_text.split())
    if total_words < 10 and not qr_url:
        logger.info("Low confidence text extracted (%d words). Triggering Gemini fallback.", total_words)
        return {"ocr_text": None, "trigger_gemini_fallback": True}
        
    return {"ocr_text": ocr_result_text, "trigger_gemini_fallback": False}

async def perform_gemini_ocr(image_bytes: bytes, api_key: str) -> Optional[str]:
    """Calls Gemini API directly with raw OCR extraction prompt to bypass captioning cascade."""
    from PIL import Image
    from io import BytesIO
    import base64
    import httpx
    
    clean_key = api_key.strip().replace('"', '').replace("'", "")
    
    # Compress and resize image to avoid payload size limits
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        out_buf = BytesIO()
        img.save(out_buf, format="JPEG", quality=80)
        processed_bytes = out_buf.getvalue()
    except Exception as compress_err:
        logger.warning("Failed to compress image for Gemini OCR: %s", compress_err)
        processed_bytes = image_bytes

    b64_image = base64.b64encode(processed_bytes).decode("utf-8")
    mime_type = "image/jpeg"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={clean_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": b64_image}},
                    {"text": "Extract all readable text, characters, URLs, and links from this image verbatim. Do not explain, describe, or summarize the image. Output only the raw extracted text."}
                ]
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates")
                if candidates and candidates[0].get("content") and candidates[0]["content"].get("parts"):
                    text_response = candidates[0]["content"]["parts"][0].get("text")
                    if text_response:
                        logger.info("Direct Gemini OCR succeeded using model: gemini-1.5-flash")
                        return text_response.strip()
            logger.warning("Direct Gemini OCR failed with status %d: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Error calling Direct Gemini OCR: %s", e)
        
    return None

async def perform_nvidia_ocr(image_bytes: bytes, api_key: str) -> Optional[str]:
    """Calls NVIDIA NIM vision models in cascade order (11b-vision -> 90b-vision -> nemotron-nano-vl)."""
    from PIL import Image
    from io import BytesIO
    import base64
    import httpx
    
    # 1. Strip whitespaces/quotes from API key defensively
    clean_key = api_key.strip().replace('"', '').replace("'", "")
    
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "Content-Type": "application/json"
    }
    
    # 2. Compress and resize image to avoid payload size limit resets (NVIDIA gateway limits)
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        out_buf = BytesIO()
        img.save(out_buf, format="JPEG", quality=80)
        processed_bytes = out_buf.getvalue()
    except Exception as compress_err:
        logger.warning("Failed to compress image for NVIDIA NIM: %s", compress_err)
        processed_bytes = image_bytes

    b64_image = base64.b64encode(processed_bytes).decode("utf-8")

    # 3. Retrieve active vision models from config & registry
    from backend.services.ai_cascade.config import settings as cascade_settings
    from backend.services.ai_cascade.registry.model_registry import ModelRegistry, ModelCapability
    
    try:
        provider_cfg = cascade_settings.get_provider_config("nvidia")
        cfg_models = provider_cfg.get("models", {})
        models = []
        for model_id, meta in cfg_models.items():
            if meta.get("status") == "active":
                try:
                    model_meta = ModelRegistry.get_model(model_id)
                    if ModelCapability.VISION in model_meta.capabilities:
                        models.append(model_id)
                except ValueError:
                    continue
    except Exception as resolve_err:
        logger.warning("Failed to resolve active vision models from registry: %s", resolve_err)
        models = []
        
    if not models:
        models = [
            "nvidia/nemotron-nano-12b-v2-vl",
            "nvidia/llama-3.2-11b-vision-instruct"
        ]
    
    for model_name in models:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all readable text, characters, URLs, and links from this image verbatim. Do not explain, describe, or summarize the image. Output only the raw extracted text."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.0
        }
        
        try:
            # Lower timeout per model so fallback transitions quickly
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    extracted = data["choices"][0]["message"]["content"].strip()
                    logger.info("NVIDIA NIM OCR succeeded using model: %s", model_name)
                    return extracted
                else:
                    logger.warning("NVIDIA NIM OCR model %s failed with status %d: %s", model_name, resp.status_code, resp.text)
        except Exception as e:
            logger.error("Error calling NVIDIA NIM OCR model %s: %s", model_name, e)
            
    return None


async def perform_ocr(img_or_path_or_bytes: Union[Image.Image, str, bytes]) -> str:
    """
    Unified entry point for performing OCR. Supports PIL Image, filepath string, or bytes.
    Enforces a cascade: Configured Provider (PaddleOCR/NVIDIA/Gemini) -> Fallbacks.
    """
    # 1. Convert input to raw bytes in memory (no disk writes)
    if isinstance(img_or_path_or_bytes, bytes):
        image_bytes = img_or_path_or_bytes
    elif isinstance(img_or_path_or_bytes, str):
        # File path
        try:
            with open(img_or_path_or_bytes, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error("Failed to read image file %s: %s", img_or_path_or_bytes, e)
            return ""
    else:
        # PIL Image
        try:
            buf = io.BytesIO()
            img_or_path_or_bytes.save(buf, format="PNG")
            image_bytes = buf.getvalue()
        except Exception as e:
            logger.error("Failed to serialize PIL Image: %s", e)
            return ""

    ocr_text = ""
    provider = getattr(settings, "OCR_PROVIDER", "local").lower()
    tried_nvidia = False

    # Direct routes
    if provider == "gemini":
        logger.info("OCR provider set to Gemini. Routing directly...")
        if settings.GEMINI_API_KEY:
            try:
                ocr_text = await perform_gemini_ocr(image_bytes, settings.GEMINI_API_KEY)
                if ocr_text:
                    return ocr_text
            except Exception as e:
                logger.error("Direct Gemini OCR failed: %s", e)
        else:
            logger.warning("Gemini OCR provider selected, but GEMINI_API_KEY is missing.")
        return ""

    elif provider == "nvidia":
        logger.info("OCR provider set to NVIDIA. Routing directly...")
        if settings.NVIDIA_API_KEY:
            try:
                ocr_text = await perform_nvidia_ocr(image_bytes, settings.NVIDIA_API_KEY)
                tried_nvidia = True
                if ocr_text and len(ocr_text.split()) >= 10:
                    return ocr_text
            except Exception as e:
                logger.error("Direct NVIDIA OCR failed: %s", e)
        else:
            logger.warning("NVIDIA OCR provider selected, but NVIDIA_API_KEY is missing.")

    # Fallback/Default route for local/remote
    if not ocr_text and provider in ("remote", "local"):
        try:
            if provider == "remote":
                try:
                    from backend.services.remote_ai_client import generate_remote_ocr
                    ocr_text = await generate_remote_ocr(image_bytes)
                except Exception as e:
                    logger.warning("Remote PaddleOCR failed: %s. Falling back to local PaddleOCR.", e)
                    provider = "local"
                    
            if provider == "local":
                if check_paddleocr_available():
                    loop = asyncio.get_running_loop()
                    executor = _get_ocr_executor()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(executor, preprocess_and_ocr_image, image_bytes),
                        timeout=120.0
                    )
                    if not result.get("trigger_gemini_fallback"):
                        ocr_text = result.get("ocr_text") or ""
        except Exception as e:
            logger.warning("PaddleOCR step failed: %s", e)

    # Fallback B: Try NVIDIA NIM OCR if PaddleOCR returned low-content or failed
    word_count = len(ocr_text.split())
    if (not ocr_text or word_count < 10) and not tried_nvidia and settings.NVIDIA_API_KEY:
        logger.info("PaddleOCR returned low-content text (%d words). Triggering NVIDIA NIM OCR fallback...", word_count)
        try:
            nvidia_text = await perform_nvidia_ocr(image_bytes, settings.NVIDIA_API_KEY)
            tried_nvidia = True
            if nvidia_text:
                logger.info("NVIDIA NIM OCR fallback succeeded. Extracted length: %d chars", len(nvidia_text))
                ocr_text = nvidia_text
        except Exception as e:
            logger.warning("NVIDIA NIM OCR fallback failed: %s", e)

    # Fallback C: Try Gemini OCR if other options returned low-content or failed
    word_count = len(ocr_text.split())
    if (not ocr_text or word_count < 10) and settings.GEMINI_API_KEY:
        logger.info("PaddleOCR/NVIDIA returned low-content text (%d words). Triggering Gemini OCR fallback...", word_count)
        try:
            gemini_text = await perform_gemini_ocr(image_bytes, settings.GEMINI_API_KEY)
            if gemini_text:
                logger.info("Gemini OCR fallback succeeded.")
                ocr_text = gemini_text
        except Exception as e:
            logger.warning("Gemini OCR fallback failed: %s", e)

    return ocr_text

