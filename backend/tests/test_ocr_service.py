import pytest
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from PIL import Image
from backend.services.ocr_service import check_paddleocr_available, perform_ocr, preprocess_and_ocr_image

@pytest.fixture(autouse=True)
def setup_ocr_provider(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "OCR_PROVIDER", "local")

# 1. Test check_paddleocr_available
def test_check_paddleocr_available():
    with patch("importlib.util.find_spec") as mock_find:
        mock_find.return_value = MagicMock()
        assert check_paddleocr_available() is True

    with patch("importlib.util.find_spec", side_effect=Exception("Failed")):
        assert check_paddleocr_available() is False

# 2. Test perform_ocr when PaddleOCR is not installed
@pytest.mark.asyncio
async def test_perform_ocr_not_installed():
    with patch("backend.services.ocr_service.check_paddleocr_available", return_value=False):
        text = await perform_ocr(b"dummy_bytes")
        assert text == ""

# 3. Test successful perform_ocr with high confidence words
@pytest.mark.asyncio
async def test_perform_ocr_success_high_confidence():
    mock_ocr = MagicMock()
    # Mock return value of ocr_client.ocr: [ [ [box, (text, conf)], ... ] ]
    mock_ocr.ocr.return_value = [
        [
            [None, ("word1 word2 word3 word4 word5", 0.95)],
            [None, ("word6 word7 word8 word9 word10", 0.90)],
        ]
    ]
    
    # Create sample 100x100 white image
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    
    with patch("backend.services.ocr_service.check_paddleocr_available", return_value=True), \
         patch("backend.services.ocr_service.get_paddle_client", return_value=mock_ocr), \
         patch("cv2.QRCodeDetector.detectAndDecode", return_value=("", None, None)), \
         patch("backend.services.ocr_service._get_ocr_executor", return_value=ThreadPoolExecutor(max_workers=1)):
         
        text = await perform_ocr(img_bytes)
        assert len(text.split()) == 10
        assert "word1" in text
        assert "word10" in text

# 4. Test perform_ocr triggering Gemini fallback (too few words)
@pytest.mark.asyncio
async def test_perform_ocr_low_confidence_fallback():
    mock_ocr = MagicMock()
    mock_ocr.ocr.return_value = [
        [
            [None, ("few words", 0.95)],
            [None, ("low conf word", 0.40)], # Low confidence, should be excluded
        ]
    ]
    
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    
    with patch("backend.services.ocr_service.check_paddleocr_available", return_value=True), \
         patch("backend.services.ocr_service.get_paddle_client", return_value=mock_ocr), \
         patch("cv2.QRCodeDetector.detectAndDecode", return_value=("", None, None)), \
         patch("backend.services.ocr_service.perform_gemini_ocr", return_value=""), \
         patch("backend.services.ocr_service.perform_nvidia_ocr", return_value=""):
         
        text = await perform_ocr(img_bytes)
        # Should return "" because trigger_gemini_fallback = True
        assert text == ""

# 5. Test QR code detection and extraction
@pytest.mark.asyncio
async def test_perform_ocr_qr_code_detected():
    mock_ocr = MagicMock()
    # Return few words so that OCR alone would trigger fallback, but QR code URL keeps it active
    mock_ocr.ocr.return_value = [
        [
            [None, ("hello", 0.95)],
        ]
    ]
    
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    
    # Mock detectAndDecode to return a valid URL
    with patch("backend.services.ocr_service.check_paddleocr_available", return_value=True), \
         patch("backend.services.ocr_service.get_paddle_client", return_value=mock_ocr), \
         patch("cv2.QRCodeDetector.detectAndDecode", return_value=("https://example.com/qr", None, None)), \
         patch("backend.services.ocr_service.perform_gemini_ocr", return_value=""), \
         patch("backend.services.ocr_service.perform_nvidia_ocr", return_value=""), \
         patch("backend.services.ocr_service._get_ocr_executor", return_value=ThreadPoolExecutor(max_workers=1)):
         
        text = await perform_ocr(img_bytes)
        # Should NOT trigger fallback, and should return the QR URL
        assert "https://example.com/qr" in text
        assert "hello" in text

# 6. Test perform_ocr timeout enforcement
@pytest.mark.asyncio
async def test_perform_ocr_timeout():
    with patch("backend.services.ocr_service.check_paddleocr_available", return_value=True), \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        text = await perform_ocr(b"some_bytes")
        assert text == ""
