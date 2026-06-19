# UI_UX_BRIEF — Recall

**Version:** 1.0  
**Scope:** Frontend visual styles, typography, animations, layout structure, and design system tokens.

---

## Design System: Cosmic Noir (Glassmorphism & Depth)

The visual design is dark-first, atmospheric, and highly immersive. It mimics a telescope viewing deep space. Instead of flat boxes and basic lines, elements float in layered planes over a space field with ambient light blobs and glowing cosmic dust.

### Color Tokens

| Token | Hex/RGBA | CSS Variable | Visual Rationale |
|-------|----------|--------------|------------------|
| **Deep Space** | `#030307` | `--bg-deep` | Bottom-most background layer (infinite void) |
| **Cosmic Base** | `#07070F` | `--bg-base` | Standard surface backing |
| **Nebula Surface** | `rgba(10, 10, 20, 0.65)` | `--surface-glass` | Frosted translucent cards; requires `backdrop-filter: blur(24px)` |
| **Galaxy Violet** | `#6C63FF` | `--color-primary` | High-importance text, active nodes, primary buttons |
| **Nebula Violet Glow** | `rgba(108, 99, 255, 0.15)` | `--color-primary-glow` | Drop shadows and background ambient blobs |
| **Mint Constellation**| `#00D4AA` | `--color-accent` | Semantic hub nodes, connection lines (edges), action icons |
| **Constellation Glow**| `rgba(0, 212, 170, 0.2)` | `--color-accent-glow` | Centroid glow and connection line pulses |
| **Starlight Text** | `#F1F1F6` | `--text-primary` | Main text; high contrast against dark glass |
| **Stardust Text** | `#8E8E9F` | `--text-secondary` | Muted labels, metadata, secondary descriptions |
| **Asteroid Border** | `rgba(255, 255, 255, 0.08)` | `--border-hairline` | Separation lines; 1px thin borders on cards and headers |

---

## Typography

- **Heading Font:** `Outfit` (Google Font) — wide, geometric, premium, futuristic feel.
- **Body & UI Labels Font:** `Inter` — neutral, clean, high readability at small scales.
- **Code & Metadata Font:** `JetBrains Mono` — high-end technical monospace, clean numbers.

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
```

---

## Mind Map — Canvas & Constellation Design

### 1. Canvas Setup
- **Renderer:** HTML5 Canvas (2D context) with GPU acceleration, resizing dynamically to full viewport.
- **Physics Engine:** Force-directed graph with Barnes-Hut repulsion calculation for fast layout processing ($O(N \log N)$).

### 2. Cosmic Visuals
- **Dynamic Background blobs:** 2–3 absolute-positioned blurred gradient blobs behind the canvas. They slowly oscillate (translate $X/Y$ using CSS animations) with 3% opacity to mimic moving nebulae.
- **Star Nodes:**
  - Nodes are drawn as **frosted circular glass disks** with a 1px hairline border (`rgba(255, 255, 255, 0.15)`).
  - Each node features a radial glow behind it. The glow radius scales proportionally with the node's connection degree (more connections = brighter star).
  - Monospace tags or icons are drawn inside the node when zoomed in.
- **Constellation Edges:**
  - Edges are drawn as curved quadratic Bezier paths (not straight lines) to give a organic, flowing feel.
  - Normal edges: Muted teal at 20% opacity.
  - Active/selected path: Glowing teal pulse that cycles along the line (animated dashes).

### 3. Node States

| State | Visual Details | Easing & Animation |
|-------|----------------|--------------------|
| **Orbital (Standard)** | Translucent violet disk, subtle base glow, small label. | Pulse effect: scale `1.0` to `1.03` dynamically when hovered. |
| **Hub (Louvain Centroid)** | Larger mint-teal disk with thick outer glowing halo. | Continuous slow rotation of the outer dashed ring. |
| **Pulse (Recently Ingested)** | White core with expanding concentric ripples. | Sine-wave opacity ripple fading out over 1000px radius. |

---

## Web Dashboard Layout

To maximize immersion, the dashboard uses a **Zero-Chrome** design. The canvas is the workspace, and UI components float over it like glass panes.

```
┌────────────────────────────────────────────────────────────────────────┐
│  [Logo]          [Search Bar (Frosted Glass)]           [Streak Badge] │ (Float Header)
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                       CANVAS (Star Field Map)                          │
│                                                                        │
│                                                   ┌──────────────────┐ │
│                                                   │ FLOATING PANEL   │ │ (360px width)
│                                                   │ Title            │ │ Frosted Glass
│                                                   │ Summary          │ │ Hairline Border
│                                                   │ Tags             │ │
│                                                   │ [Quiz] [Remind]  │ │
│                                                   └──────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### Floating Side Panel
- Slides in from the right edge on node click using `cubic-bezier(0.16, 1, 0.3, 1)` easing.
- Glassmorphic card styling with border-top glow highlight.
- Closing triggered by clicking empty canvas background or pressing `Escape`.

---

## Telegram Mini App (TWA) Layout

Because a force-directed graph is frustratingly cramped in a small 200px viewport, Recall uses a **Dual-View sliding Tab system** on mobile.

```
┌──────────────────────────────────┐
│  [Search Bar]      [View Toggle] │ Header
├──────────────────────────────────┤
│                                  │
│           MAIN VIEW              │
│                                  │
│   Tab 1: Star Map (Full Screen)  │ -> Full drag, zoom, pinch gestures
│   Tab 2: Star List (Scrollable)  │ -> Frosted list cards
│                                  │
├──────────────────────────────────┤
│    [Map View]       [List View]  │ Sliding Bottom Navigation Bar
└──────────────────────────────────┘
```

### Interaction Specifications
1. **Pinch & Zoom:** Map View allows full zoom. Tap target hit boxes expand to `44x44px` on mobile using transparent bounding rects (`hitSlop` in React Native).
2. **Press Feedback:** All list cards and action buttons scale down slightly on press (`scale: 0.97`) with a 100ms transition.
3. **Haptic Integration:** Every primary interaction (navigating views, node selection, answering quizzes) triggers an OS haptic feedback pulse (Impact Light/Medium).

---

## Motion & Micro-interactions

All animation curves must adhere to physics-based motions to feel organic rather than rigid.

- **Panel Transitions:** `cubic-bezier(0.16, 1, 0.3, 1)` (custom Ease-Out).
- **Scale Spring:** Modals and panels spring open with `damping: 20` and `stiffness: 90`.
- **Exit Transitions:** Must execute 1.5x faster than enter transitions to keep the interface feeling responsive.
