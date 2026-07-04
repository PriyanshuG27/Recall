import pytest
from backend.services.drive_sync import GoogleDocBuilder

def test_google_doc_builder():
    builder = GoogleDocBuilder()
    builder.start_paragraph()
    builder.append_run("Recall Knowledge Base", bold=True)
    builder.end_paragraph(style="HEADING_1")

    assert "Recall Knowledge Base" in builder.text
    assert len(builder.requests) == 2
    assert "updateParagraphStyle" in builder.requests[-1]
