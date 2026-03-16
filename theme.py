import re
import json
"""
theme.py — stylesheet loading and theme application.

HOW THEMING WORKS
-----------------
style.qss uses a small set of named token hex values (see DARK_TOKENS below).
apply_theme() builds a token→value mapping for the current theme, then does a
single-pass substitution on the raw QSS text before passing it to Qt.

Themes are loaded from JSON files in the themes/ directory alongside this file.
Each JSON file contains a flat dict of token→hex mappings plus an optional
"name" key for display in the UI.  The app ships with dark.json and light.json
as defaults, but users can add their own — just drop a .json file in themes/.

If no themes/ folder exists (e.g. in a stripped binary), the app falls back to
the hardcoded DARK_TOKENS / _light_tokens() values and works normally.

JSON THEME FORMAT
-----------------
{
  "name":       "My Theme",       // display name (optional, defaults to filename)
  "base":       "dark",           // "dark" or "light" — which built-in to start from
  "surface_hi": "#1a4070",        // hover fills, active inputs
  "surface":    "#0f3460",        // input backgrounds, pressed states, borders
  "panel":      "#16213e",        // toolbar, side panel backgrounds
  "bg":         "#1a1a2e",        // window / dialog background
  "canvas":     "#0d0d1a",        // graphics view background
  "text":       "#eaeaea",        // primary text
  "text_white": "#ffffff",        // text on coloured buttons
  "textdim":    "#8888aa",        // secondary text, borders
  "accent":     "#e94560"         // accent colour (overridden by user picker)
}

Any omitted keys fall back to the base theme's values.

ADDING A THEME VARIANT IN CODE
-------------------------------
Add a new function alongside _light_tokens() and wire it into _tokens_for().
"""

from pathlib import Path
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

# ── canonical dark-theme tokens ───────────────────────────────────────────────
# These exact hex strings MUST appear in style.qss — they are the substitution
# anchors.  Do not change these values without updating style.qss to match.
DARK_TOKENS = {
    "surface_hi": "#1a4070",  # hover fills, active inputs, lighter surfaces
    "surface":    "#0f3460",  # input backgrounds, pressed states, borders
    "panel":      "#16213e",  # toolbar, side panel, list backgrounds
    "bg":         "#1a1a2e",  # window / dialog background
    "canvas":     "#0d0d1a",  # graphics view background
    "text":       "#eaeaea",  # primary text
    "text_white": "#ffffff",  # white text on coloured buttons
    "textdim":    "#8888aa",  # secondary / placeholder text, subtle borders
    "accent":     "#e94560",  # accent — overridden by user-chosen colour
}


def _light_tokens(accent: str) -> dict:
    """Built-in light theme token values."""
    return {
        "surface_hi": "#cad4e8",
        "surface":    "#b8c4d8",
        "panel":      "#dde1ea",
        "bg":         "#f0f2f5",
        "canvas":     "#c0c4d0",
        "text":       "#1a1a2e",
        "text_white": "#1a1a2e",
        "textdim":    "#555577",
        "accent":     accent,
    }


def _dark_tokens(accent: str) -> dict:
    """Built-in dark theme token values."""
    return {**DARK_TOKENS, "accent": accent}


# ── resource / themes directory ───────────────────────────────────────────────

def resource_dir() -> Path:
    """
    Return the directory containing bundled resources (style.qss, icons/, themes/).
    Uses sys._MEIPASS when running as a PyInstaller bundle.
    """
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def themes_dir() -> Path:
    return resource_dir() / "themes"


def icon_variant(theme_name: str) -> str:
    """
    Return "dark" or "light" icon variant for the given theme name.
    Reads the JSON 'base' field; falls back to name-based guess.
    """
    td = themes_dir()
    if td.exists():
        for p in td.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                if data.get("name") == theme_name:
                    return data.get("base", "dark").lower()
            except Exception:
                pass
    return "light" if "light" in theme_name.lower() else "dark"


# ── theme discovery ───────────────────────────────────────────────────────────

def list_themes() -> list[tuple[str, Path]]:
    """
    Return a list of (display_name, path) for all available themes.

    Scans themes/ for *.json files.  Falls back to the two built-in themes
    ("Dark", "Light") if the directory is missing or empty.
    """
    td = themes_dir()
    results = []
    if td.exists():
        for p in sorted(td.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                name = data.get("name") or p.stem.replace("_", " ").title()
                results.append((name, p))
            except Exception:
                pass  # skip malformed files silently

    if not results:
        # Fallback — no JSON files found, advertise the two built-ins
        results = [("Dark", None), ("Light", None)]

    return results


def load_theme_tokens(theme_name: str, accent: str) -> dict:
    """
    Build a complete token dict for the given theme name and accent colour.

    Resolution order:
      1. Find the JSON file whose display name matches theme_name.
      2. Start from its "base" ("dark"/"light") built-in values.
      3. Override with any keys present in the JSON.
      4. Always override "accent" with the user's chosen colour.

    Falls back to dark built-in if nothing matches.
    """
    themes = list_themes()

    # Find matching JSON path
    json_path = None
    for name, path in themes:
        if name == theme_name and path is not None:
            json_path = path
            break

    if json_path is None:
        # No JSON — use built-in based on name substring
        if "light" in theme_name.lower():
            return _light_tokens(accent)
        return _dark_tokens(accent)

    try:
        data = json.loads(json_path.read_text())
    except Exception:
        return _dark_tokens(accent)

    # Start from the base theme
    base = data.get("base", "dark").lower()
    tokens = _light_tokens(accent) if base == "light" else _dark_tokens(accent)

    # Apply overrides from JSON (skip meta keys)
    meta = {"name", "base"}
    for key, value in data.items():
        if key not in meta and key in DARK_TOKENS:
            tokens[key] = value

    # User's accent always wins
    tokens["accent"] = accent
    return tokens


# ── QSS loading ───────────────────────────────────────────────────────────────

def load_qss(qss_dir: Path | None = None) -> str:
    """
    Load style.qss.  Returns empty string if missing — app still runs unstyled.
    """
    search = qss_dir or resource_dir()
    qss_path = search / "style.qss"
    if qss_path.exists():
        return qss_path.read_text()
    return ""


# ── theme application ─────────────────────────────────────────────────────────

def apply_theme(cfg: dict, canvas_sel_items: list | None = None,
                qss_dir: Path | None = None) -> None:
    """
    Apply the current theme from cfg to the running QApplication.

    cfg keys used:
        theme  — display name of the theme (must match a name from list_themes())
        accent — hex colour string, e.g. "#e94560"
    """
    accent     = cfg.get("accent", DARK_TOKENS["accent"])
    theme_name = cfg.get("theme", "Dark")

    # Normalise legacy "dark"/"light" values saved before JSON themes
    if theme_name == "dark":
        theme_name = "Dark"
    elif theme_name == "light":
        theme_name = "Light"

    tokens = load_theme_tokens(theme_name, accent)

    global CURRENT_TOKENS
    CURRENT_TOKENS = tokens

    qss = load_qss(qss_dir)

    # Substitute tokens — text_white (#ffffff) must run BEFORE bg,
    # because some themes set bg=#ffffff which would otherwise get
    # clobbered by the text_white substitution on the next pass.
    priority = ["text_white"]  # must substitute before any token whose
                                # value could equal #ffffff
    ordered = priority + [k for k in DARK_TOKENS if k not in priority]
    for key in ordered:
        qss = qss.replace(DARK_TOKENS[key], tokens[key])

    # Scale font sizes
    scale = cfg.get("font_scale", 1.0)
    if scale != 1.0:
        def _scale_pt(m):
            return f"{max(1, round(int(m.group(1)) * scale))}pt"
        qss = re.sub(r"(\d+)pt", _scale_pt, qss)

    app = QApplication.instance()
    if app:
        app.setStyleSheet(qss)

    _update_colour_globals(accent, cfg)

    if canvas_sel_items:
        for item in canvas_sel_items:
            item.set_active(item._active)
            item._sync()


# ── runtime colour globals ────────────────────────────────────────────────────

C_BG       = QColor(DARK_TOKENS["bg"])
C_PANEL    = QColor(DARK_TOKENS["panel"])
C_OVERLAY  = "#ff0000"
OVERLAY_ALPHA = 76
C_ACCENT   = QColor(DARK_TOKENS["accent"])
C_GREEN    = QColor("#27ae60")
C_TEXT     = QColor(DARK_TOKENS["text"])
C_TEXTDIM  = QColor(DARK_TOKENS["textdim"])
C_HANDLE   = QColor("#ffd700")
C_SEL      = QColor(DARK_TOKENS["accent"])
C_SEL_ACT  = QColor(DARK_TOKENS["accent"]).lighter(130)

CURRENT_TOKENS: dict = dict(DARK_TOKENS)


def _update_colour_globals(accent: str, cfg: dict | None = None) -> None:
    global C_ACCENT, C_SEL, C_SEL_ACT, C_OVERLAY, OVERLAY_ALPHA
    C_ACCENT  = QColor(accent)
    C_SEL     = QColor(accent)
    C_SEL_ACT = QColor(accent).lighter(130)
    if cfg:
        C_OVERLAY     = cfg.get("overlay_color",   "#ff0000")
        OVERLAY_ALPHA = round(cfg.get("overlay_opacity", 30) * 255 / 100)
