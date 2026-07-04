import pytest
from datetime import datetime
from backend.services.okf_service import serialize_item_to_okf, parse_okf_to_item

def test_serialize_and_parse_okf():
    now = datetime.now()
    okf_str = serialize_item_to_okf(
        title="OKF Spec",
        tags=["okf", "spec"],
        created_at=now,
        source_url="https://example.com/okf",
        context_note="Important note",
        category="url",
        content="Body content of the note"
    )

    assert "title: OKF Spec" in okf_str
    assert "source_url: https://example.com/okf" in okf_str
    assert "Body content of the note" in okf_str

    parsed = parse_okf_to_item(okf_str)
    assert parsed["title"] == "OKF Spec"
    assert "okf" in parsed["tags"]
    assert parsed["source_url"] == "https://example.com/okf"
    assert parsed["raw_text"] == "Body content of the note"

def test_parse_okf_empty_and_string_tags():
    assert parse_okf_to_item("")["title"] == "Untitled Note"

    yaml_str = """---
title: Single Tag Note
tags: "single_tag"
---

Body text
"""
    parsed = parse_okf_to_item(yaml_str)
    assert parsed["tags"] == ["single_tag"]
