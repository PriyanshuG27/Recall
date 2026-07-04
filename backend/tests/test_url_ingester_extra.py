import pytest
import os
from backend.services.url_ingester import _clean_google_doc_title, _write_temp_pdf_content, _parse_url_html

def test_clean_google_doc_title():
    html = "<html><head><title>System Design Spec - Google Docs</title></head><body></body></html>"
    title = _clean_google_doc_title(html)
    assert title == "System Design Spec"

def test_parse_url_html():
    html = "<html><head><title>My Article</title></head><body><h1>Header</h1><script>alert(1);</script><p>Article content</p></body></html>"
    title, text = _parse_url_html(html)
    assert title == "My Article"
    assert "Article content" in text
    assert "alert(1)" not in text

def test_write_temp_pdf_content():
    content = b"%PDF-1.4 sample content"
    tmp_path = _write_temp_pdf_content(content)
    assert os.path.exists(tmp_path)
    assert tmp_path.endswith(".pdf")
    os.remove(tmp_path)
