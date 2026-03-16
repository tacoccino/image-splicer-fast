#!/usr/bin/env python3
"""
Image Splicer — entry point.

Run:  python main.py

Dependencies are auto-installed on first run if missing.
"""

import sys


def _install(pkg: str) -> None:
    import subprocess
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", pkg,
         "--break-system-packages", "-q"])


# ── ensure dependencies are available ────────────────────────────────────────

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    _install("PyQt6")
    from PyQt6.QtWidgets import QApplication

try:
    from PIL import Image  # noqa: F401 — just checking it's installed
except ImportError:
    _install("Pillow")

# ── application entry point ───────────────────────────────────────────────────

from pathlib import Path
from PyQt6.QtGui import QIcon
from theme  import load_qss
from window import MainWindow


def _app_icon() -> QIcon:
    """
    Load the application icon from the icons/ directory.
    Looks for icon.png (or .icns on Mac, .ico on Windows) next to main.py.
    Falls back gracefully if the file isn't found.
    """
    base = Path(__file__).parent
    import platform
    candidates = [
        base / "icon.icns",   # macOS native (best quality in dock)
        base / "icon.ico",    # Windows native (multi-size)
        base / "icon.png",    # universal fallback
    ]
    for path in candidates:
        if path.exists():
            return QIcon(str(path))
    return QIcon()


def main() -> None:
    app = QApplication(sys.argv)

    # Fusion style ensures QPushButton colours are respected on all platforms.
    # macOS's native Aqua style ignores background/border on buttons.
    app.setStyle("Fusion")
    app.setStyleSheet(load_qss())

    icon = _app_icon()
    app.setWindowIcon(icon)   # taskbar / dock icon

    win = MainWindow()
    win.setWindowIcon(icon)   # title bar icon
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
