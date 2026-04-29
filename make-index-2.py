#!/usr/bin/env python3
"""
make-index-2.py

Generates source/index-2.html — the new fancy landing page for Lady Wisdom's House —
from source/synopsis.yaml.  The build-and-publish.sh script calls this before
build-website.py, which then copies the result to the docs/ directory.

Usage:
    python make-index-2.py [--output PATH] [--force Y|N]
"""

import argparse
import os
import sys
import yaml

# ---------------------------------------------------------------------------
# Timing constants (seconds) — adjust here without touching the HTML/JS
# ---------------------------------------------------------------------------
SCROLL_PAUSE_SECONDS   = 5    # pause duration after each automatic scroll step
RESUME_IDLE_SECONDS    = 15   # resume scrolling after user pauses and does nothing
SCROLL_SPEED_PX_S      = 80   # pixels per second for automatic scrolling
# ---------------------------------------------------------------------------

def load_articles(yaml_path: str) -> list[dict]:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def html_for_articles(articles: list[dict]) -> str:
    """Return the JS array literal for article data and the tile HTML."""
    # Build JS array so the page can shuffle on load
    js_items = []
    tile_htmls = []
    for i, art in enumerate(articles):
        title    = art.get("title", "")
        sub      = art.get("sub", "")
        synopsis = art.get("synopsis", "")
        source   = art.get("source", "")
        href     = source.replace(".md", ".html") if source else "#"

        # JS data record (for shuffling)
        sub_js = sub.replace("'", "\\'") if sub else ""
        title_js = title.replace("'", "\\'")
        synopsis_js = synopsis.replace("'", "\\'")
        js_items.append(
            f"  {{title:'{title_js}', sub:'{sub_js}', synopsis:'{synopsis_js}', href:'{href}'}}"
        )

        # Static tile (hidden by default; JS will render the shuffled set)
        sub_html = f'<div class="tile-sub">{sub}</div>' if sub else ""
        tile_htmls.append(
            f'<a class="tile" href="{href}" data-index="{i}">'
            f'<div class="tile-title">{title}</div>'
            f'{sub_html}'
            f'<div class="tile-synopsis">{synopsis}</div>'
            f'</a>'
        )

    js_array = "[\n" + ",\n".join(js_items) + "\n]"
    return js_array, "\n".join(tile_htmls)


def build_html(articles: list[dict]) -> str:
    js_array, _tiles_static = html_for_articles(articles)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lady Wisdom's House</title>
<link rel="stylesheet" href="./styles/colors.css" type="text/css">

<style>
/* ============================================================
   Root / reset
   ============================================================ */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  min-height: 100vh;
  background: var(--dark-cerulean);
  color: #e8f0f5;
  font-family: "Segoe UI", Optima, Helvetica, Arial, sans-serif;
  display: flex;
  flex-direction: column;
  overflow: hidden;   /* prevent page-level scroll; carousel owns it */
}}

/* ============================================================
   Blueprint watermark overlay
   ============================================================ */
body::before {{
  content: "";
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
  z-index: 0;
}}

/* ============================================================
   Header
   ============================================================ */
.site-header {{
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 24px 10px;
  background: linear-gradient(135deg, #0a2a52 0%, #154085 60%, #1a5080 100%);
  border-bottom: 2px solid var(--coral-blue);
  box-shadow: 0 3px 14px rgba(0,0,0,.55);
  flex-shrink: 0;
}}

.site-header a.logo-link {{
  display: flex;
  align-items: center;
  flex-shrink: 0;
}}

.site-header img.logo {{
  height: 64px;
  width: auto;
  border: 1px solid var(--coral-blue);
  border-radius: 4px;
  box-shadow: 0 0 8px rgba(162,222,237,.4);
}}

.header-text {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}

.site-title {{
  font-family: Optima, "Palatino Linotype", Georgia, serif;
  font-size: clamp(1.4rem, 4vw, 2.4rem);
  font-weight: 700;
  letter-spacing: .04em;
  color: var(--chiffon);
  text-shadow: 0 2px 8px rgba(0,0,0,.7);
}}

.site-subtitle {{
  font-size: clamp(.75rem, 1.8vw, 1rem);
  color: var(--sea-mist);
  font-style: italic;
  letter-spacing: .02em;
}}

/* ============================================================
   Carousel wrapper
   ============================================================ */
.carousel-wrapper {{
  position: relative;
  z-index: 5;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 20px 0 12px;
}}

/* ============================================================
   Track — HORIZONTAL (tablet / desktop landscape)
   ============================================================ */
.track {{
  display: flex;
  width: max-content;
  gap: 20px;
  padding: 8px 24px 16px;
  cursor: grab;
  user-select: none;
}}
.track:active {{ cursor: grabbing; }}

/* ============================================================
   VERTICAL layout for portrait / narrow phones
   ============================================================ */
@media (max-aspect-ratio: 3/4) {{
  body {{ overflow: hidden; }}

  /* wrapper stays flex-column; track overflows it and is clipped */
  .carousel-wrapper {{
    overflow: hidden;
  }}

  .track {{
    flex-direction: column;
    padding: 8px 16px 16px;
    height: max-content;
    width: 100% !important;
    gap: 16px;
  }}

  .tile {{
    width: 100% !important;
    min-height: unset;
  }}
}}

/* ============================================================
   Tiles
   ============================================================ */
.tile {{
  flex-shrink: 0;
  width: clamp(260px, 30vw, 380px);
  min-height: 280px;
  background: linear-gradient(160deg, #0e3a6a 0%, #0b2d55 100%);
  border: 1px solid var(--coral-blue);
  border-radius: 8px;
  padding: 20px 18px 16px;
  box-shadow:
    0 4px 18px rgba(0,0,0,.5),
    inset 0 1px 0 rgba(162,222,237,.15);
  text-decoration: none;
  color: inherit;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: box-shadow .25s, border-color .25s, transform .2s;
  position: relative;
  overflow: hidden;
}}

/* Blueprint corner accent */
.tile::before {{
  content: "";
  position: absolute;
  top: 0; right: 0;
  width: 36px; height: 36px;
  border-top: 2px solid var(--light-gray-teal);
  border-right: 2px solid var(--light-gray-teal);
  border-radius: 0 8px 0 0;
  opacity: .5;
  pointer-events: none;
}}
.tile::after {{
  content: "";
  position: absolute;
  bottom: 0; left: 0;
  width: 36px; height: 36px;
  border-bottom: 2px solid var(--light-gray-teal);
  border-left: 2px solid var(--light-gray-teal);
  border-radius: 0 0 0 8px;
  opacity: .5;
  pointer-events: none;
}}

.tile:hover,
.tile.paused-hover {{
  border-color: var(--light-gray-teal);
  box-shadow:
    0 6px 28px rgba(0,0,0,.7),
    0 0 0 2px rgba(136,192,196,.35),
    inset 0 1px 0 rgba(162,222,237,.25);
  transform: translateY(-3px);
}}

.tile-title {{
  font-family: Optima, "Palatino Linotype", Georgia, serif;
  font-size: clamp(.95rem, 1.8vw, 1.15rem);
  font-weight: 700;
  color: var(--chiffon);
  line-height: 1.25;
  border-bottom: 1px solid rgba(162,222,237,.25);
  padding-bottom: 6px;
}}

.tile-sub {{
  font-size: .82rem;
  font-style: italic;
  color: var(--sea-mist);
  letter-spacing: .02em;
}}

.tile-synopsis {{
  font-size: clamp(.78rem, 1.4vw, .9rem);
  line-height: 1.55;
  color: #c8dce8;
  flex: 1 1 auto;
  overflow: hidden;
  /* Subtle gradient fade if text overflows */
  -webkit-mask-image: linear-gradient(to bottom, #000 80%, transparent 100%);
  mask-image: linear-gradient(to bottom, #000 80%, transparent 100%);
}}

/* ============================================================
   Progress pip strip
   ============================================================ */
.pip-strip {{
  position: relative;
  z-index: 10;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  padding: 6px 0 10px;
  flex-shrink: 0;
}}

.pip {{
  width: 8px; height: 8px;
  border-radius: 50%;
  background: rgba(162,222,237,.3);
  transition: background .3s;
}}
.pip.active {{
  background: var(--coral-blue);
}}

/* ============================================================
   Pause indicator
   ============================================================ */
.pause-badge {{
  position: fixed;
  bottom: 18px;
  right: 18px;
  z-index: 20;
  background: rgba(10,40,80,.85);
  border: 1px solid var(--coral-blue);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: .78rem;
  color: var(--sea-mist);
  letter-spacing: .04em;
  opacity: 0;
  transition: opacity .35s;
  pointer-events: none;
}}
.pause-badge.visible {{ opacity: 1; }}
</style>
</head>

<body>

<!-- ============================================================
     Header
     ============================================================ -->
<header class="site-header">
  <a class="logo-link" href="home.html" aria-label="Go to Home">
    <img class="logo" src="images/wisdom-house.png" alt="Lady Wisdom's House logo"/>
  </a>
  <div class="header-text">
    <div class="site-title">Lady Wisdom's House</div>
    <div class="site-subtitle">Exploring biblical wisdom, prophetic patterns, and the architecture of Scripture</div>
  </div>
</header>

<!-- ============================================================
     Carousel
     ============================================================ -->
<div class="carousel-wrapper" id="carouselWrapper">
  <div class="track" id="track" role="list" aria-label="Article index"></div>
</div>

<!-- Progress pips -->
<div class="pip-strip" id="pipStrip" aria-hidden="true"></div>

<!-- Pause badge -->
<div class="pause-badge" id="pauseBadge">⏸ paused</div>

<!-- ============================================================
     Embedded JavaScript — no external libraries
     ============================================================ -->
<script>
/* ---- timing constants (generated from Python) ---- */
const SCROLL_PAUSE_MS  = {SCROLL_PAUSE_SECONDS * 1000};
const RESUME_IDLE_MS   = {RESUME_IDLE_SECONDS  * 1000};
const SCROLL_SPEED     = {SCROLL_SPEED_PX_S};   /* px / second */

/* ---- article data (shuffled on load) ---- */
const ARTICLES = {js_array};

/* ---- Fisher-Yates shuffle ---- */
function shuffle(arr) {{
  for (let i = arr.length - 1; i > 0; i--) {{
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }}
  return arr;
}}

/* ---- build tiles ---- */
function buildTiles(articles) {{
  const track = document.getElementById("track");
  track.innerHTML = "";
  articles.forEach((art, i) => {{
    const a = document.createElement("a");
    a.className = "tile";
    a.href = art.href;
    a.setAttribute("role", "listitem");
    a.dataset.index = i;

    const titleEl = document.createElement("div");
    titleEl.className = "tile-title";
    titleEl.textContent = art.title;
    a.appendChild(titleEl);

    if (art.sub) {{
      const subEl = document.createElement("div");
      subEl.className = "tile-sub";
      subEl.textContent = art.sub;
      a.appendChild(subEl);
    }}

    const synEl = document.createElement("div");
    synEl.className = "tile-synopsis";
    synEl.textContent = art.synopsis;
    a.appendChild(synEl);

    track.appendChild(a);
  }});
}}

/* ---- build pip strip ---- */
function buildPips(count) {{
  const strip = document.getElementById("pipStrip");
  strip.innerHTML = "";
  for (let i = 0; i < count; i++) {{
    const d = document.createElement("div");
    d.className = "pip";
    strip.appendChild(d);
  }}
}}

function updatePip(idx) {{
  document.querySelectorAll(".pip").forEach((p, i) => p.classList.toggle("active", i === idx));
}}

/* ============================================================
   Carousel engine
   ============================================================ */
(function () {{
  const articles = shuffle([...ARTICLES]);
  buildTiles(articles);
  buildPips(articles.length);

  const track   = document.getElementById("track");
  const badge   = document.getElementById("pauseBadge");
  const wrapper = document.getElementById("carouselWrapper");

  /* ---- axis helpers ---- */
  const isPortrait = () => (window.innerWidth / window.innerHeight) < (3 / 4);

  /* Total scrollable distance: how far the track extends past the viewport */
  function getScrollMax() {{
    return isPortrait()
      ? Math.max(0, track.scrollHeight - wrapper.clientHeight)
      : Math.max(0, track.scrollWidth  - wrapper.clientWidth);
  }}

  /* Move the track with CSS transform — reliable on all browsers including iOS Safari.
     Using scrollLeft/scrollTop on overflow:hidden elements is unreliable on iOS. */
  function applyPos(px) {{
    const max  = getScrollMax();
    currentPos = Math.max(0, Math.min(px, max));
    if (isPortrait()) {{
      track.style.transform = `translateY(-${{currentPos}}px)`;
    }} else {{
      track.style.transform = `translateX(-${{currentPos}}px)`;
    }}
    const frac   = max > 0 ? currentPos / max : 0;
    const pipIdx = Math.round(frac * (articles.length - 1));
    updatePip(pipIdx);
  }}

  /* ---- state ---- */
  let paused         = false;
  let idleTimer      = null;
  let animFrameId    = null;
  let lastTimestamp  = null;
  let accumulated    = 0;
  let currentPos     = 0;
  let pauseCountdown = 0;
  let inPause        = false;
  let prevPortrait   = isPortrait();

  /* ---- pause / resume ---- */
  function showBadge() {{ badge.classList.add("visible"); }}
  function hideBadge() {{ badge.classList.remove("visible"); }}

  function pauseAuto() {{
    paused        = true;
    lastTimestamp = null;
    showBadge();
    clearTimeout(idleTimer);
    idleTimer = setTimeout(resumeAuto, RESUME_IDLE_MS);
  }}

  function resumeAuto() {{
    paused        = false;
    inPause       = false;
    lastTimestamp = null;
    hideBadge();
    clearTimeout(idleTimer);
  }}

  /* ---- animation loop ---- */
  function animate(ts) {{
    animFrameId = requestAnimationFrame(animate);
    if (paused) {{ lastTimestamp = null; return; }}
    if (lastTimestamp === null) {{ lastTimestamp = ts; return; }}

    const delta = ts - lastTimestamp;
    lastTimestamp = ts;

    if (inPause) {{
      pauseCountdown -= delta;
      if (pauseCountdown <= 0) inPause = false;
      return;
    }}

    accumulated += SCROLL_SPEED * (delta / 1000);
    if (accumulated >= 1) {{
      const step = Math.floor(accumulated);
      accumulated -= step;
      const max = getScrollMax();
      if (max <= 0) {{ accumulated = 0; return; }}  /* layout not ready */
      const newPos = currentPos + step;
      if (newPos >= max) {{
        /* Reached end — jump back to start with a pause */
        applyPos(0);
        inPause        = true;
        pauseCountdown = SCROLL_PAUSE_MS;
      }} else {{
        applyPos(newPos);
        /* Brief pause every ~300 px so each tile is readable */
        if (Math.floor(newPos / 300) > Math.floor((newPos - step) / 300)) {{
          inPause        = true;
          pauseCountdown = SCROLL_PAUSE_MS;
        }}
      }}
    }}
  }}

  /* ---- drag / touch ---- */
  let dragStartClient = 0;
  let dragStartPos    = 0;
  let isDragging      = false;
  let dragMoved       = false;

  /* Return the scroll-axis coordinate from any pointer or touch event */
  function getCoord(e) {{
    const src = (e.touches && e.touches.length > 0)
               ? e.touches[0]
               : (e.changedTouches && e.changedTouches.length > 0)
               ? e.changedTouches[0]
               : e;
    return isPortrait() ? src.clientY : src.clientX;
  }}

  function onPointerDown(e) {{
    if (e.type === "mousedown" && e.button !== 0) return;
    dragStartClient = getCoord(e);
    dragStartPos    = currentPos;
    isDragging      = true;
    dragMoved       = false;
    paused          = true;
    lastTimestamp   = null;
    showBadge();
    clearTimeout(idleTimer);
    /* Auto-resume if the user doesn't drag or navigate within idle timeout */
    idleTimer = setTimeout(resumeAuto, RESUME_IDLE_MS);
    /* Block text-selection on mouse drag; do NOT preventDefault for touch
       so the browser can still synthesise click/tap events for short taps */
    if (e.type === "mousedown") e.preventDefault();
  }}

  function onPointerMove(e) {{
    if (!isDragging) return;
    const coord = getCoord(e);
    const diff  = dragStartClient - coord;
    if (Math.abs(diff) > 6) {{
      dragMoved = true;
      /* Now confirmed drag — prevent native scroll / page pan */
      e.preventDefault();
    }}
    if (dragMoved) {{
      applyPos(dragStartPos + diff);
      /* Reset idle timer while dragging */
      clearTimeout(idleTimer);
      idleTimer = setTimeout(resumeAuto, RESUME_IDLE_MS);
    }}
  }}

  function onPointerUp(e) {{
    if (!isDragging) return;
    isDragging = false;
    /* idleTimer is already running and will auto-resume */
  }}

  /* Mouse */
  track.addEventListener("mousedown",  onPointerDown, {{ passive: false }});
  window.addEventListener("mousemove", onPointerMove);
  window.addEventListener("mouseup",   onPointerUp);

  /* Touch — touchstart is passive so the browser handles taps normally;
     only touchmove calls preventDefault (after drag threshold is exceeded) */
  track.addEventListener("touchstart", onPointerDown, {{ passive: true }});
  track.addEventListener("touchmove",  onPointerMove, {{ passive: false }});
  track.addEventListener("touchend",   onPointerUp);

  /* Hover: pause on enter, resume on leave (mouse only) */
  track.addEventListener("mouseenter", () => {{ if (!isDragging) pauseAuto(); }});
  track.addEventListener("mouseleave", () => {{ if (!isDragging) resumeAuto(); }});

  /* Click: block navigation only when a real drag just occurred */
  track.addEventListener("click", (e) => {{
    if (dragMoved) e.preventDefault();
  }});

  /* Orientation / resize: reset scroll position when portrait<->landscape flips */
  window.addEventListener("resize", () => {{
    const nowPortrait = isPortrait();
    if (nowPortrait !== prevPortrait) {{
      prevPortrait          = nowPortrait;
      currentPos            = 0;
      accumulated           = 0;
      inPause               = false;
      track.style.transform = "";
    }}
    applyPos(currentPos);
  }});

  /* bfcache: when the user presses Back to return to this page,
     resume scrolling immediately rather than staying paused */
  window.addEventListener("pageshow", (e) => {{
    if (e.persisted) resumeAuto();
  }});

  /* Kick off */
  animate(performance.now());
}})();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build index-2.html from synopsis.yaml")
    parser.add_argument(
        "--output",
        default="./index-2.html",
        help="Path for the generated HTML file (default: ./index-2.html)",
    )
    parser.add_argument(
        "--force",
        default="N",
        choices=["Y", "N", "y", "n"],
        help="Replace existing file without prompting (Y/N, default N)",
    )
    args = parser.parse_args()

    output_path = args.output
    force = args.force.upper() == "Y"

    # Prompt if file exists and --force not set
    if os.path.exists(output_path) and not force:
        answer = input(f"File '{output_path}' already exists. Overwrite? [Y/N]: ").strip().upper()
        if answer != "Y":
            print("Aborted — file not created.")
            sys.exit(0)

    # Resolve synopsis.yaml relative to this script's location
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    yaml_path    = os.path.join(script_dir, "source", "synopsis.yaml")
    if not os.path.exists(yaml_path):
        # Fallback: maybe we're already inside source/
        yaml_path = os.path.join(script_dir, "synopsis.yaml")
    if not os.path.exists(yaml_path):
        print(f"ERROR: Cannot find synopsis.yaml (looked in {script_dir}/source/ and {script_dir}/)")
        sys.exit(1)

    articles = load_articles(yaml_path)
    html     = build_html(articles)

    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Created {output_path}  ({len(articles)} article tiles)")


if __name__ == "__main__":
    main()
