"""
backend/services/ocr_service.py
===============================
Enhanced local OCR service wrapper utilizing PIL image preprocessing,
OpenCV QR code detection, and in-memory local PaddleOCR with confidence filtering.
Executes completely in memory without temporary files, enforcing a 30s timeout.
"""

import io
import logging
import asyncio
from typing import Dict, Union, Optional
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

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
    """Retrieves the cached singleton PaddleOCR client."""
    global _paddle_client
    if _paddle_client is None:
        if not check_paddleocr_available():
            raise RuntimeError("PaddleOCR or PaddlePaddle is not installed/available.")
        from paddleocr import PaddleOCR
        # Instantiate with silent logging to prevent stdout pollution
        _paddle_client = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _paddle_client

def preprocess_and_ocr_image(image_bytes: bytes) -> dict:
    """
    Performs PIL preprocessing, OpenCV QR code detection, and PaddleOCR
    with confidence filtering on image bytes. Runs entirely in memory.
    """
    import numpy as np
    import cv2
    image = Image.open(io.BytesIO(image_bytes))
    
    # 1. Detect QR code URL first using OpenCV on original image
    qr_url = None
    try:
        open_cv_image = np.array(image)
        if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 3:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
        elif len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 4:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2BGR)
            
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(open_cv_image)
        if data and data.strip().lower().startswith(("http://", "https://", "www.")):
            qr_url = data.strip()
            logger.info("Successfully extracted QR code URL: %s", qr_url)
    except Exception as qr_err:
        logger.warning("In-memory QR code detection failed: %s", qr_err)
        
    # 2. PIL Image Preprocessing
    # A. Convert to grayscale & enhance contrast & sharpen
    image = image.convert('L')
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    
    # B. Resize if width < 800px
    if image.width < 800:
        ratio = 1200.0 / image.width
        image = image.resize((1200, int(image.height * ratio)), Image.Resampling.LANCZOS)
        
    # C. Adaptive binarization & convert back to 'L' grayscale (uint8)
    image = image.point(lambda p: 0 if p < 128 else 255, '1')
    image = image.convert('L')
    
    # 3. PaddleOCR with confidence filtering (>= 60%)
    high_conf_words = []
    try:
        ocr_client = get_paddle_client()
        img_np = np.array(image)
        
        # PaddleOCR expects grayscale (H, W) or BGR (H, W, 3)
        result = ocr_client.ocr(img_np)
        
        if result and result[0]:
            for line in result[0]:
                if line and len(line) > 1 and line[1]:
                    text = line[1][0]
                    conf = line[1][1]
                    if conf >= 0.60 and text.strip():
                        # Split detected line into individual words
                        words = text.strip().split()
                        high_conf_words.extend(words)
    except Exception as ocr_err:
        logger.error("In-memory PaddleOCR execution failed: %s", ocr_err)
        
    ocr_result_text = " ".join(high_conf_words)
    
    # Append QR code URL to OCR text if found
    if qr_url:
        if ocr_result_text:
            ocr_result_text = ocr_result_text + "\n" + qr_url
        else:
            ocr_result_text = qr_url

    # 4. Fallback trigger check (fewer than 10 words and no QR URL)
    total_words = len(ocr_result_text.split())
    if total_words < 10 and not qr_url:
        logger.info("Low confidence text extracted (%d words). Triggering Gemini fallback.", total_words)
        return {"ocr_text": None, "trigger_gemini_fallback": True}
        
    return {"ocr_text": ocr_result_text, "trigger_gemini_fallback": False}

async def perform_ocr(img_or_path_or_bytes: Union[Image.Image, str, bytes]) -> str:
    """
    Unified entry point for performing OCR. Supports PIL Image, filepath string, or bytes.
    Enforces a strict 30-second processing timeout per image.
    """
    if not check_paddleocr_available():
        logger.warning("PaddleOCR not installed. OCR skipped.")
        return ""
        
    # Convert input to raw bytes in memory (no disk writes)
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

    try:
        loop = asyncio.get_running_loop()
        # Enforce 30-second timeout on the CPU-bound preprocessing and OCR task
        result = await asyncio.wait_for(
            loop.run_in_executor(None, preprocess_and_ocr_image, image_bytes),
            timeout=30.0
        )
        if result.get("trigger_gemini_fallback"):
            return ""
        return result.get("ocr_text") or ""
    except asyncio.TimeoutError:
        logger.error("OCR preprocessing and extraction timed out after 30 seconds.")
        return ""
    except Exception as e:
        logger.error("Exception in perform_ocr pipeline: %s", e)
        return ""
