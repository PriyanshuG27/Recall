import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def serialize_item_to_okf(
    title: Optional[str],
    tags: Optional[List[str]],
    created_at: Any,
    source_url: Optional[str],
    context_note: Optional[str],
    category: Optional[str],
    content: Optional[str]
) -> str:
    """
    Serializes database item attributes into a standard Google Open Knowledge Format (OKF) Markdown block.
    Includes a YAML frontmatter header followed by the note content body.
    """
    yaml_lines = [
        "---",
        f"title: {title or 'Untitled Note'}",
    ]
    
    # Process tags
    if tags:
        # Sort for deterministic output and format as standard YAML list
        clean_tags = sorted(list(set(str(t).strip().lower() for t in tags if t)))
        tags_str = ", ".join(f'"{t}"' for t in clean_tags)
        yaml_lines.append(f"tags: [{tags_str}]")
    else:
        yaml_lines.append("tags: []")

    # Process created_at date
    if created_at:
        if hasattr(created_at, "strftime"):
            date_str = created_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = str(created_at)
        yaml_lines.append(f"saved_date: {date_str}")
        
    if source_url:
        yaml_lines.append(f"source_url: {source_url}")
        
    if context_note:
        # Use json.dumps to escape special chars/quotes in standard JSON format
        yaml_lines.append(f"context_note: {json.dumps(context_note)}")
        
    if category:
        yaml_lines.append(f"category: {category}")
        
    yaml_lines.append("---")
    
    frontmatter = "\n".join(yaml_lines)
    return f"{frontmatter}\n\n{content or ''}"

def parse_okf_to_item(content_str: str) -> Dict[str, Any]:
    """
    Parses an OKF Markdown file into a dictionary of item attributes.
    Reads YAML frontmatter using standard library regular expressions, avoiding PyYAML dependency.
    """
    if not content_str:
        return {
            "title": "Untitled Note",
            "tags": [],
            "source_url": None,
            "context_note": None,
            "category": "text",
            "raw_text": ""
        }

    # Split by frontmatter delimiter
    parts = content_str.split("---", 2)
    yaml_data: Dict[str, Any] = {}
    body_content = content_str
    
    if len(parts) >= 3:
        yaml_str = parts[1]
        body_content = parts[2].strip()
        
        # Parse lines manually
        for line in yaml_str.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                
                # Check for array/list pattern: tags: ["tag1", "tag2"]
                if val.startswith("[") and val.endswith("]"):
                    items_list = [item.strip().strip('"\'') for item in val[1:-1].split(",") if item.strip()]
                    yaml_data[key] = items_list
                else:
                    # Strip outer single or double quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    
                    # Decrypt json string if context_note
                    if key == "context_note":
                        try:
                            # Re-add double quotes to parse with json.loads if it was stringified
                            if not (val.startswith('"') and val.endswith('"')):
                                val = json.loads(f'"{val}"')
                            else:
                                val = json.loads(val)
                        except Exception:
                            pass
                    yaml_data[key] = val

    # Normalise fields
    title = yaml_data.get("title")
    tags = yaml_data.get("tags") or []
    if isinstance(tags, str):
        # Handle string fallback if tags: "[tag1, tag2]"
        if tags.startswith("[") and tags.endswith("]"):
            tags = [t.strip().strip('"\'') for t in tags[1:-1].split(",") if t.strip()]
        else:
            tags = [tags]
    elif not isinstance(tags, list):
        tags = []
        
    tags = sorted(list(set(str(t).strip().lower() for t in tags if t)))
    
    # Extract saved_date if present
    saved_date = yaml_data.get("saved_date")
    
    return {
        "title": title or "Untitled Note",
        "tags": tags,
        "source_url": yaml_data.get("source_url"),
        "context_note": yaml_data.get("context_note"),
        "category": yaml_data.get("category") or "text",
        "raw_text": body_content,
        "saved_date": saved_date
    }
