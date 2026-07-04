import pytest
from backend.services.image_ingester import extract_urls_from_ocr

def test_extract_urls_from_ocr_multiline():
    text = "https://github.com/PriyanshuG27\nhttps://recall.app/dashboard"
    urls = extract_urls_from_ocr(text)
    assert "https://github.com/PriyanshuG27" in urls
    assert "https://recall.app/dashboard" in urls
