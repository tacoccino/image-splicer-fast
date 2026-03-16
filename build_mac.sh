#!/bin/bash
# =============================================================================
# build_mac.sh — Build Image Splicer as a macOS .app bundle
#
# Usage:
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Output:
#   dist/mac/Image Splicer.app
#
# Requirements:
#   pip install pyinstaller
# =============================================================================

set -e

APP_NAME="Image Splicer"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist/mac"
WORK_DIR="$SCRIPT_DIR/build/mac"

echo "==> Building $APP_NAME for macOS"
echo "    Source: $SCRIPT_DIR"

# ── Check PyInstaller is available ───────────────────────────────────────────
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "    Installing PyInstaller..."
    pip install pyinstaller --break-system-packages -q
fi

# ── App icon ─────────────────────────────────────────────────────────────────
ICON_ARG=""
if [ -f "$SCRIPT_DIR/icon.icns" ]; then
    ICON_ARG="--icon $SCRIPT_DIR/icon.icns"
elif [ -f "$SCRIPT_DIR/icon.png" ]; then
    ICON_ARG="--icon $SCRIPT_DIR/icon.png"
fi

# ── Icons folder ─────────────────────────────────────────────────────────────
ICONS_ARG=""
if [ -d "$SCRIPT_DIR/icons" ]; then
    ICONS_ARG="--add-data $SCRIPT_DIR/icons:icons"
fi

# ── Themes folder ────────────────────────────────────────────────────────────
THEMES_ARG=""
if [ -d "$SCRIPT_DIR/image_splicer/themes" ]; then
    THEMES_ARG="--add-data $SCRIPT_DIR/image_splicer/themes:themes"
fi

# ── Run PyInstaller ───────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

python3 -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --distpath "$DIST_DIR" \
    --workpath "$WORK_DIR" \
    --specpath "$WORK_DIR" \
    --add-data "$SCRIPT_DIR/style.qss:." \
    $ICONS_ARG \
    $THEMES_ARG \
    $ICON_ARG \
    --hidden-import PyQt6.sip \
    --collect-all PyQt6 \
    "$SCRIPT_DIR/main.py"

echo ""
echo "==> Done!  App bundle:"
echo "    $DIST_DIR/$APP_NAME.app"
echo ""
echo "    To run:       open \"$DIST_DIR/$APP_NAME.app\""
echo "    To distribute: zip the .app or drag to /Applications"
