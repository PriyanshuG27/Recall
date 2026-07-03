"""
backend/services/mind_map_service.py
====================================
Generates dynamic, dark-themed SVG mind map snapshots representing the user's
semantic knowledge clusters as vibrant glowing star constellations.
"""

import math
import logging
from typing import Dict, Any, List
import psycopg

logger = logging.getLogger(__name__)

async def generate_weekly_svg_mind_map(cur: psycopg.AsyncCursor, user_id: int) -> str:
    """
    Generates a dark-themed SVG string representing the user's top tags and their connections
    using vibrant, high-contrast neon gradient stars.
    """
    # 1. Fetch top tags from the last 7 days
    await cur.execute(
        """
        SELECT unnest(tags) as tag, COUNT(*) as count
        FROM items
        WHERE user_id = %s 
          AND created_at >= NOW() - INTERVAL '7 days' 
          AND tags IS NOT NULL
        GROUP BY tag
        ORDER BY count DESC
        LIMIT 5;
        """,
        (user_id,)
    )
    recent_tags = await cur.fetchall()
    
    # 2. If we found fewer than 5 tags, merge with overall top tags to ensure a rich graph
    tags_dict = {tag: count for tag, count in recent_tags}
    if len(tags_dict) < 5:
        await cur.execute(
            """
            SELECT unnest(tags) as tag, COUNT(*) as count
            FROM items
            WHERE user_id = %s 
              AND tags IS NOT NULL
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 10;
            """,
            (user_id,)
        )
        overall_tags = await cur.fetchall()
        for tag, count in overall_tags:
            if tag not in tags_dict:
                tags_dict[tag] = count
            if len(tags_dict) >= 5:
                break
                
    # Format sorted list of top tags
    top_tags = sorted(tags_dict.items(), key=lambda x: -x[1])[:5]
    
    if not top_tags:
        # Default empty state SVG
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">'
            '<style>@import url("https://fonts.googleapis.com/css2?family=Outfit:wght@300;600&amp;display=swap");</style>'
            '<rect width="500" height="500" fill="#0B0F19" />'
            '<text x="250" y="230" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-weight="600" font-size="16" fill="#F3F4F6">No constellation mapped yet</text>'
            '<text x="250" y="260" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-size="12" fill="#9CA3AF">Save some items to see your weekly mind map!</text>'
            '</svg>'
        )

    # 3. Position calculations (Width: 500, Height: 500)
    # Define an asymmetric, organic network layout for up to 5 nodes to look like a designer constellation map
    layout_offsets = [
        {"x": 250, "y": 250, "color_start": "#C084FC", "color_end": "#7C3AED"},  # Node 1: Purple
        {"x": 120, "y": 140, "color_start": "#60A5FA", "color_end": "#2563EB"},  # Node 2: Blue
        {"x": 380, "y": 120, "color_start": "#2DD4BF", "color_end": "#0D9488"},  # Node 3: Teal
        {"x": 150, "y": 360, "color_start": "#FBBF24", "color_end": "#D97706"},  # Node 4: Amber
        {"x": 350, "y": 340, "color_start": "#F472B6", "color_end": "#DB2777"}   # Node 5: Pink
    ]
    
    nodes = []
    for i, (tag, count) in enumerate(top_tags):
        offset = layout_offsets[i % len(layout_offsets)]
        
        # Calculate size scale based on item count relative to center node
        size_ratio = count / top_tags[0][1] if top_tags[0][1] > 0 else 1.0
        r = int(34 + 14 * min(1.0, size_ratio))
        if i == 0:
            r = 54  # Dominant focus node
            
        nodes.append({
            "tag": tag.upper(),
            "count": count,
            "x": offset["x"],
            "y": offset["y"],
            "radius": r,
            "color_start": offset["color_start"],
            "color_end": offset["color_end"]
        })

    # 4. Query co-occurring items to build connection paths
    await cur.execute(
        "SELECT tags FROM items WHERE user_id = %s AND tags IS NOT NULL;",
        (user_id,)
    )
    items_tags_rows = await cur.fetchall()
    
    # Create co-occurrence edges
    edges = []
    
    # Draw connections from center node to all other active tags
    for i in range(1, len(nodes)):
        edges.append({
            "x1": nodes[0]["x"], "y1": nodes[0]["y"],
            "x2": nodes[i]["x"], "y2": nodes[i]["y"],
            "weight": 3.0,
            "color": nodes[i]["color_start"]
        })
        
    # Draw mutual edges between orbiting nodes if they share common items
    for i in range(1, len(nodes)):
        for j in range(i + 1, len(nodes)):
            tag1 = nodes[i]["tag"].lower()
            tag2 = nodes[j]["tag"].lower()
            
            # Count how many items contain both tags
            shared_count = sum(1 for (row_tags,) in items_tags_rows if tag1 in row_tags and tag2 in row_tags)
            if shared_count > 0:
                edges.append({
                    "x1": nodes[i]["x"], "y1": nodes[i]["y"],
                    "x2": nodes[j]["x"], "y2": nodes[j]["y"],
                    "weight": 1.5,
                    "color": "#475569"
                })

    # 5. Build SVG XML String
    svg_header = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="500" height="500">\n'
        '  <style>\n'
        '    @import url("https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800;900&amp;display=swap");\n'
        '  </style>\n'
        '  <defs>\n'
        '    <!-- Deep space background -->\n'
        '    <radialGradient id="bg" cx="50%" cy="50%" r="75%">\n'
        '      <stop offset="0%" stop-color="#111827" />\n'
        '      <stop offset="60%" stop-color="#0B0F19" />\n'
        '      <stop offset="100%" stop-color="#030712" />\n'
        '    </radialGradient>\n'
        '    <!-- Ambient Nebula glow -->\n'
        '    <radialGradient id="nebula" cx="50%" cy="50%" r="55%">\n'
        '      <stop offset="0%" stop-color="#6366F1" stop-opacity="0.12" />\n'
        '      <stop offset="100%" stop-color="#6366F1" stop-opacity="0" />\n'
        '    </radialGradient>\n'
        '    <!-- High-end bloom filter -->\n'
        '    <filter id="bloom" x="-50%" y="-50%" width="200%" height="200%">\n'
        '      <feGaussianBlur stdDeviation="12" result="blur" />\n'
        '      <feMerge>\n'
        '        <feMergeNode in="blur" />\n'
        '        <feMergeNode in="SourceGraphic" />\n'
        '      </feMerge>\n'
        '    </filter>\n'
        '    <!-- Text shadow filter for extreme readability -->\n'
        '    <filter id="text_shadow" x="-20%" y="-20%" width="140%" height="140%">\n'
        '      <feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.8"/>\n'
        '    </filter>\n'
    )
    
    # Dynamically inject radial gradients for vibrant star orbs
    gradients = ""
    for i, node in enumerate(nodes):
        gradients += (
            f'    <radialGradient id="grad_{i}" cx="40%" cy="40%" r="60%">\n'
            f'      <stop offset="0%" stop-color="#FFFFFF" />\n'
            f'      <stop offset="25%" stop-color="{node["color_start"]}" />\n'
            f'      <stop offset="100%" stop-color="{node["color_end"]}" />\n'
            f'    </radialGradient>\n'
        )
        
    svg_defs = gradients + '  </defs>\n\n'
    
    # Background and subtle cosmic glow
    svg_bg = (
        '  <!-- Background -->\n'
        '  <rect width="500" height="500" fill="url(#bg)" />\n\n'
        '  <!-- Nebula Atmosphere -->\n'
        '  <circle cx="250" cy="250" r="240" fill="url(#nebula)" />\n\n'
        '  <!-- Cosmic Star Dust Particles -->\n'
        '  <g fill="#FFFFFF" opacity="0.2">\n'
        '    <circle cx="70" cy="80" r="1" /><circle cx="430" cy="190" r="1.5" />\n'
        '    <circle cx="150" cy="270" r="1" /><circle cx="330" cy="70" r="2" />\n'
        '    <circle cx="210" cy="380" r="1.5" /><circle cx="410" cy="410" r="1" />\n'
        '    <circle cx="80" cy="420" r="1" /><circle cx="300" cy="200" r="1.5" />\n'
        '  </g>\n\n'
    )
    
    # Connecting edges (filament glowing lines)
    svg_edges = '  <!-- Connection Filaments -->\n'
    for edge in edges:
        # Glow path
        svg_edges += (
            f'  <line x1="{edge["x1"]}" y1="{edge["y1"]}" x2="{edge["x2"]}" y2="{edge["y2"]}" '
            f'stroke="{edge["color"]}" stroke-width="4.5" stroke-opacity="0.15" filter="url(#bloom)"/>\n'
        )
        # Foreground thin structural path
        svg_edges += (
            f'  <line x1="{edge["x1"]}" y1="{edge["y1"]}" x2="{edge["x2"]}" y2="{edge["y2"]}" '
            f'stroke="{edge["color"]}" stroke-width="1.25" stroke-opacity="0.6" stroke-dasharray="3 4" />\n'
        )
    svg_edges += "\n"
    
    # Nodes rendering
    svg_nodes = '  <!-- Celestial Neon Star Nodes -->\n'
    for i, node in enumerate(nodes):
        # Outer soft atmosphere halo
        svg_nodes += (
            f'  <circle cx="{node["x"]}" cy="{node["y"]}" r="{node["radius"] + 18}" '
            f'fill="{node["color_start"]}" fill-opacity="0.10" filter="url(#bloom)"/>\n'
        )
        # Fine accent scale ring
        svg_nodes += (
            f'  <circle cx="{node["x"]}" cy="{node["y"]}" r="{node["radius"] + 8}" '
            f'fill="none" stroke="{node["color_start"]}" stroke-width="1" stroke-opacity="0.4" stroke-dasharray="6 3"/>\n'
        )
        # Inner vibrant orb circle
        svg_nodes += (
            f'  <circle cx="{node["x"]}" cy="{node["y"]}" r="{node["radius"]}" '
            f'fill="url(#grad_{i})" stroke="#FFFFFF" stroke-width="1.5" stroke-opacity="0.8" filter="url(#bloom)"/>\n'
        )
        
    # Text labels overlay
    svg_labels = '\n  <!-- Labels Overlay -->\n'
    for node in nodes:
        # Inside the glassmorphic circle: uppercase label + signals count
        svg_labels += (
            f'  <g transform="translate({node["x"]}, {node["y"]})">\n'
            f'    <text x="0" y="2" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-weight="900" font-size="10px" fill="#FFFFFF" letter-spacing="1" filter="url(#text_shadow)">#{node["tag"]}</text>\n'
            f'    <text x="0" y="14" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-weight="600" font-size="7px" fill="#F3F4F6" letter-spacing="0.5" filter="url(#text_shadow)">{node["count"]} SIGNALS</text>\n'
            f'  </g>\n'
        )
        
    # Headers/Footers decoration
    svg_footer = (
        '\n  <!-- Header Title -->\n'
        '  <text x="250" y="55" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-weight="900" font-size="12" fill="#FFFFFF" letter-spacing="4" filter="url(#text_shadow)">RECALL CONSTELLATION</text>\n'
        '  <text x="250" y="70" text-anchor="middle" font-family="\'Outfit\', sans-serif" font-weight="400" font-size="7" fill="#9CA3AF" letter-spacing="2">WEEKLY COGNITIVE PERSPECTIVE</text>\n'
        '</svg>\n'
    )
    
    return svg_header + svg_defs + svg_bg + svg_edges + svg_nodes + svg_labels + svg_footer
