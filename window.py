"""
window.py — MainWindow: application shell and top-level controller.

MainWindow owns the toolbar, splitter, canvas, side panel, and status bar.
It wires together all the other modules and handles:
  • File open / drag-and-drop
  • Saving crops (in a background thread)
  • Settings dialog
  • Theme application
  • Keyboard shortcuts
"""

import os
import platform
import threading
from pathlib import Path

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QSize
from PyQt6.QtGui  import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QMainWindow, QWidget, QLabel, QPushButton,
                              QCheckBox, QFrame, QHBoxLayout, QVBoxLayout,
                              QSplitter, QStatusBar, QFileDialog, QMessageBox)

from config  import load_cfg, save_cfg
from models  import Sel
from canvas  import Canvas
from panels  import Toast, SidePanel
from dialogs import SettingsDialog
import theme as th


# Icons live in  icons/dark/  and  icons/light/
# The correct subfolder is picked automatically from the current theme.
# resource_dir() resolves correctly both from source and PyInstaller bundles.
_ICONS_ROOT = th.resource_dir() / "icons"
_ICON_SIZE  = QSize(20, 20)

def _icon(name: str, theme: str = "dark") -> QIcon | None:
    """
    Load an icon for the given theme variant ("dark" or "light").
    Falls back to the other variant if the themed version is missing,
    then to None if neither exists.
    """
    for variant in (theme, "dark", "light"):
        path = _ICONS_ROOT / variant / f"{name}.png"
        if path.exists():
            return QIcon(str(path))
    return None


def _toolbar_btn(text: str, tooltip: str, style_id: str = "",
                 icon_name: str = "", theme: str = "dark",
                 parent=None) -> QPushButton:
    """
    Create a flat toolbar button.
    If icon_name is given and the icon file exists, the button shows only
    the icon (no text).  Otherwise falls back to the text label.
    """
    ico = _icon(icon_name, theme) if icon_name else None
    if ico:
        b = QPushButton("", parent)
        b.setIcon(ico)
        b.setIconSize(_ICON_SIZE)
    else:
        b = QPushButton(text, parent)
    if style_id:
        b.setObjectName(style_id)
    b.setToolTip(tooltip)
    return b


def _vsep() -> QFrame:
    """Thin vertical separator for the toolbar."""
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setObjectName("accent_sep")
    f.setFixedWidth(2)
    return f


class MainWindow(QMainWindow):
    """
    Top-level application window.

    Keep this class focused on *coordination* — it should delegate
    rendering to Canvas/SidePanel and business logic to the helper modules.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Splicer")
        self.setMinimumSize(1100, 600)

        self.cfg        = load_cfg()
        self._mac       = platform.system() == "Darwin"
        self._mod       = "Cmd" if self._mac else "Ctrl"
        self._panel_open = True   # tracks panel visibility for icon state

        self._build_ui()
        self._build_shortcuts()
        th.apply_theme(self.cfg)
        self._update_panel_icon()
        self.statusBar().showMessage(
            "Open an image to get started — or drag & drop a file onto the window.")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Canvas must be created before the toolbar so button signals can connect
        self.canvas = Canvas()
        self.canvas.on_load      = self._try_load
        self.canvas.on_coords    = self._update_coords
        self.canvas.refresh_list = self._refresh_list
        self.canvas.on_sel_hover = self._on_sel_hover
        self.canvas.on_sel_leave = self._on_sel_leave
        self.canvas.zoom_speed   = self.cfg.get("zoom_speed", 1.0)

        root.addWidget(self._build_toolbar())

        # Splitter: canvas | side panel
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.addWidget(self.canvas)

        self.side = SidePanel()
        self.side.set_name_change_callback(self._on_sel_name_change)
        self.side.set_row_click_callback(self._on_row_click)
        self.side.prefix_edit.setText(self.cfg.get("prefix", "crop"))
        self.side.prefix_edit.textChanged.connect(
            lambda t: self._persist("prefix", t.strip() or "crop"))
        self.side.keep_chk.setChecked(self.cfg.get("keep_sels", True))
        self.side.keep_chk.stateChanged.connect(
            lambda: self._persist("keep_sels", self.side.keep_chk.isChecked()))
        self._splitter.addWidget(self.side)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([850, 310])
        root.addWidget(self._splitter, stretch=1)

        # Status bar
        self.setStatusBar(QStatusBar())
        self._coord_lbl = QLabel("")
        self._coord_lbl.setObjectName("dimmed")
        self.statusBar().addPermanentWidget(self._coord_lbl)

        # Toast notification overlay
        self._toast = Toast(self.canvas)

        # Set initial panel icon state after everything is wired up
        # (deferred so _icon_btns dict exists — toolbar builds first)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setObjectName("toolbar")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        m = self._mod
        t = th.icon_variant(self.cfg.get("theme", "Dark"))

        # Track icon names so we can swap them when the theme changes
        self._icon_btns: dict = {}  # QPushButton → icon_name

        def ibtn(text, tooltip, style_id="", icon_name=""):
            b = _toolbar_btn(text, tooltip, style_id, icon_name, theme=t)
            if icon_name:
                self._icon_btns[b] = icon_name
            return b

        # Left-side buttons
        self._btn_open     = ibtn("⊞  Open Image",  f"Open image ({m}+O)", "accent",  "open")
        self._btn_save     = ibtn("✦  Save Crops",  f"Save all crops ({m}+S)", "green", "save")
        self._btn_open_dir = ibtn("📂  Open Folder", "Open save location folder", "grey",  "folder")
        self._btn_del      = ibtn("⌫  Delete",  "Delete selected crops  (Delete / Backspace)", "grey",  "delete")
        self._btn_clear    = ibtn("✕  Clear All",   "Clear all crops", "clear_danger", "clear")
        self._btn_settings = ibtn("⚙  Settings",   f"Settings ({m}+,)", icon_name="settings")

        self._btn_overlay  = ibtn("⬚  Overlay", f"Toggle crop overlay  ({m}+T)",
                                   icon_name="overlay")
        self._btn_select_all = ibtn("⊞  Select All", f"Select all crops  ({m}+A)",
                                     icon_name="select_all")
        self._btn_deselect   = ibtn("◻  Deselect", "Deselect all crops  (Escape)",
                                     icon_name="deselect")

        for w in (self._btn_open, self._btn_save, self._btn_open_dir,
                  _vsep(), self._btn_del, self._btn_select_all,
                  self._btn_deselect, self._btn_clear,
                  _vsep(), self._btn_overlay, _vsep(), self._btn_settings):
            lay.addWidget(w)

        lay.addStretch()

        # Right-side zoom controls + panel toggle
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFixedWidth(48)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_fit   = ibtn("⊡", f"Fit image to window  ({m}+0)", icon_name="fit")
        self._btn_zin   = ibtn("+", f"Zoom in  ({m}+=  or  {m}+Scroll)",  icon_name="zoom_in")
        self._btn_zout  = ibtn("−", f"Zoom out  ({m}+−  or  {m}+Scroll)", icon_name="zoom_out")
        self._btn_panel = ibtn("▐", f"Show/hide crops panel  ({self._mod}+\\)")
        for b in (self._btn_fit, self._btn_zin, self._btn_zout, self._btn_panel):
            b.setFixedWidth(38)

        zoom_lbl = QLabel("Zoom:")
        zoom_lbl.setObjectName("dimmed")
        for w in (zoom_lbl, self._zoom_lbl,
                  self._btn_fit, self._btn_zin, self._btn_zout,
                  _vsep(), self._btn_panel):
            lay.addWidget(w)

        # Connect signals
        self._btn_open.clicked.connect(self._open_file)
        self._btn_overlay.clicked.connect(self._toggle_overlay)
        self._btn_select_all.clicked.connect(self.canvas.select_all)
        self._btn_deselect.clicked.connect(self.canvas.deselect_all)
        self._btn_save.clicked.connect(self._save_crops)
        self._btn_open_dir.clicked.connect(self._open_save_dir)
        self._btn_del.clicked.connect(self.canvas.delete_active)
        self._btn_clear.clicked.connect(self.canvas.clear_all)
        self._btn_settings.clicked.connect(self._open_settings)
        self._btn_fit.clicked.connect(self._zoom_fit)
        self._btn_zin.clicked.connect(self._zoom_in)
        self._btn_zout.clicked.connect(self._zoom_out)
        self._btn_panel.clicked.connect(self._toggle_panel)

        return tb

    def _build_shortcuts(self) -> None:
        m = "Ctrl"  # Qt maps Ctrl→Cmd on macOS automatically

        def sc(key, fn):
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        sc(f"{m}+O",    self._open_file)
        sc(f"{m}+S",    self._save_crops)
        sc(f"{m}+,",    self._open_settings)
        sc(f"{m}+Z",    self.canvas.delete_last)
        sc(f"{m}+=",    self._zoom_in)
        sc(f"{m}++",    self._zoom_in)
        sc(f"{m}+-",    self._zoom_out)
        sc(f"{m}+0",    self._zoom_fit)
        sc("Delete",    self.canvas.delete_active)
        sc("Backspace", self.canvas.delete_active)
        sc("Escape",    self._cancel_or_deselect)
        sc(f"{m}+A",    self.canvas.select_all)
        sc(f"{m}+T",    self._toggle_overlay)
        sc(f"{m}+\\",  self._toggle_panel)

    # ── zoom ──────────────────────────────────────────────────────────────────

    def _zoom_in(self) -> None:
        self.canvas.zoom_in()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _zoom_out(self) -> None:
        self.canvas.zoom_out()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _zoom_fit(self) -> None:
        self.canvas.zoom_fit()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _cancel_draw(self) -> None:
        if self.canvas._drawing and self.canvas._rubber:
            self.canvas.scene.removeItem(self.canvas._rubber)
            self.canvas._rubber  = None
            self.canvas._drawing = False

    def _cancel_or_deselect(self) -> None:
        """Escape: cancel active draw first; if none, deselect all."""
        if self.canvas._drawing and self.canvas._rubber:
            self._cancel_draw()
        else:
            self.canvas.deselect_all()

    def _toggle_overlay(self) -> None:
        """Toggle semi-transparent fill overlay on all selections."""
        active = self.canvas.toggle_overlay()
        self._update_overlay_icon(active)

    def _update_overlay_icon(self, active: bool) -> None:
        t = th.icon_variant(self.cfg.get("theme", "Dark"))
        name = "overlay_on" if active else "overlay"
        ico  = _icon(name, t)
        if ico:
            self._btn_overlay.setIcon(ico)
            self._btn_overlay.setIconSize(_ICON_SIZE)
            self._btn_overlay.setText("")

    # ── panel toggle ──────────────────────────────────────────────────────────

    def _toggle_panel(self) -> None:
        self._panel_open = not self._panel_open
        if not self._panel_open:
            self._panel_width = self._splitter.sizes()[1]
            self.side.hide()
            self._btn_panel.setToolTip("Show crops panel")
        else:
            self.side.show()
            w     = getattr(self, "_panel_width", 210)
            total = sum(self._splitter.sizes())
            self._splitter.setSizes([total - w, w])
            self._btn_panel.setToolTip("Hide crops panel")
        self._update_panel_icon()

    # ── status / coord display ────────────────────────────────────────────────

    def _update_coords(self, x, y) -> None:
        self._coord_lbl.setText("" if x is None else f"x:{x}  y:{y}")

    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _on_sel_hover(self, idx: int, part: str) -> None:
        # NOTE: internally "sel" = crop region; "selected" = active/highlighted state
        """Show contextual hints in the status bar when hovering a crop."""
        m = self._mod
        if part == "move":
            hint = "Drag to move  ·  Alt+drag to duplicate  ·  Right-click for more"
        else:
            hint = "Drag edge/corner to resize"
        self.statusBar().showMessage(hint)

    def _on_sel_leave(self) -> None:
        """Restore normal status when cursor leaves a selection."""
        self._refresh_list()

    # ── selections list ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self.side.refresh(self.canvas.sels, self.canvas.primary,
                          self.canvas.delete_sel,
                          self.canvas.active_sels)
        n      = len(self.canvas.sels)
        active = self.canvas.primary
        nsel   = len(self.canvas.active_sels)
        if nsel > 1:
            self._status(f"{nsel} crops selected   |   {n} total")
        elif active is not None and active < n:
            s = self.canvas.sels[active]
            self._status(
                f"Crop #{active+1} — {int(s.width())}×{int(s.height())}px"
                f"   |   {n} total")
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _on_sel_name_change(self) -> None:
        """Refresh canvas labels when the user edits a selection name."""
        for item in self.canvas.sel_items:
            item._sync()

    def _on_row_click(self, idx: int, shift: bool) -> None:
        """Badge click in side panel — select or Shift+add to selection."""
        self.canvas.activate_sel(idx, add=shift)

    # ── file handling ─────────────────────────────────────────────────────────

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif);;All Files (*)")
        if path:
            self._try_load(path)

    def _try_load(self, path: str) -> None:
        """Load an image, optionally preserving fitting selections."""
        from PIL import Image  # local import — only needed here

        path = path.strip()
        if not os.path.isfile(path):
            QMessageBox.critical(self, "Error", f"File not found:\n{path}")
            return
        try:
            new_img = Image.open(path)
            new_img.load()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open image:\n{e}")
            return

        # Snapshot any selections that fit inside the new image
        restore: list[tuple] = []
        if (self.canvas.sels and self.canvas.pil_img
                and self.side.keep_chk.isChecked()):
            for s in self.canvas.sels:
                if s.fits_in(new_img.width, new_img.height):
                    restore.append((*s.rect(), s.name))

        self.canvas.clear_all()
        self.canvas.load_image(new_img)

        for item in restore:
            s = self.canvas.add_sel(*item[:4])
            if len(item) > 4:
                s.name = item[4]
        self.canvas.deactivate()
        self._refresh_list()

        self.setWindowTitle(f"Image Splicer — {Path(path).name}")
        extra = f"  — kept {len(restore)} crop(s)" if restore else ""
        self._status(
            f"Loaded: {Path(path).name}  "
            f"({new_img.width}×{new_img.height}px){extra}")
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    # ── save ──────────────────────────────────────────────────────────────────

    def _open_save_dir(self) -> None:
        sd = self.cfg.get("save_dir", "").strip()
        if not sd or not os.path.isdir(sd):
            QMessageBox.warning(self, "No Save Location",
                "Set a save location in Settings first.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(sd))

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        # Explicitly apply the app stylesheet to the dialog — on Windows,
        # top-level dialogs don't always inherit QApplication.styleSheet()
        from PyQt6.QtWidgets import QApplication
        dlg.setStyleSheet(QApplication.instance().styleSheet())
        if dlg.exec():
            self.cfg = dlg.result_cfg
            save_cfg(self.cfg)
            th.apply_theme(self.cfg, self.canvas.sel_items)
            self._reload_icons()
            self.canvas.zoom_speed = self.cfg.get("zoom_speed", 1.0)
            self._refresh_list()  # re-apply active row highlight in new theme
            self._status("Settings saved.")

    def _reload_icons(self) -> None:
        """Swap all toolbar icons to match the current theme."""
        t = th.icon_variant(self.cfg.get("theme", "Dark"))
        for btn, name in self._icon_btns.items():
            ico = _icon(name, t)
            if ico:
                btn.setIcon(ico)
                btn.setIconSize(_ICON_SIZE)
                btn.setText("")
        self._update_panel_icon()
        self._update_overlay_icon(self.canvas.overlay_mode)

    def _update_panel_icon(self) -> None:
        """Set the panel toggle button icon from self._panel_open state."""
        t = th.icon_variant(self.cfg.get("theme", "Dark"))
        name = "panel_open" if self._panel_open else "panel_closed"
        ico  = _icon(name, t)
        if ico:
            self._btn_panel.setIcon(ico)
            self._btn_panel.setIconSize(_ICON_SIZE)
            self._btn_panel.setText("")
        else:
            self._btn_panel.setIcon(QIcon())
            self._btn_panel.setText("▐" if self._panel_open else "▌")

    def _persist(self, key: str, val) -> None:
        self.cfg[key] = val
        save_cfg(self.cfg)

    def _save_crops(self) -> None:
        if not self.canvas.pil_img:
            QMessageBox.warning(self, "No Image", "Open an image first.")
            return
        if not self.canvas.sels:
            QMessageBox.warning(self, "No Crops",
                "Define at least one crop region first.")
            return
        sd = self.cfg.get("save_dir", "")
        if not sd or not os.path.isdir(sd):
            QMessageBox.warning(self, "No Save Location",
                "Set a save location in Settings first.")
            return

        # Snapshot everything we need before handing off to the thread
        prefix  = self.side.prefix_edit.text().strip() or "crop"
        fmt     = self.cfg.get("format", "PNG")
        quality = self.cfg.get("jpeg_quality", 90)
        ext     = "jpg" if fmt == "JPEG" else fmt.lower()
        pil_img = self.canvas.pil_img
        sels    = list(self.canvas.sels)  # shallow copy; Sel is mutable but coords won't change mid-save

        def worker():
            saved, errors = [], []
            for i, s in enumerate(sels):
                ix1 = max(0,          min(int(s.ix1), int(s.ix2)))
                iy1 = max(0,          min(int(s.iy1), int(s.iy2)))
                ix2 = min(pil_img.width,  max(int(s.ix1), int(s.ix2)))
                iy2 = min(pil_img.height, max(int(s.iy1), int(s.iy2)))
                if ix2 <= ix1 or iy2 <= iy1:
                    errors.append(f"#{i+1}: zero-size crop")
                    continue
                crop  = pil_img.crop((ix1, iy1, ix2, iy2))
                slug  = s.filename_slug(i + 1)
                base  = f"{prefix}_{slug}"
                fname = f"{base}.{ext}"
                n = 1
                while os.path.exists(os.path.join(sd, fname)):
                    fname = f"{base}_{n}.{ext}"
                    n += 1
                try:
                    save_kw = {"quality": quality} if fmt == "JPEG" else {}
                    crop.save(os.path.join(sd, fname), fmt, **save_kw)
                    saved.append(fname)
                except Exception as e:
                    errors.append(f"#{i+1}: {e}")

            if errors:
                self._invoke_toast(f"⚠ " + "\n".join(errors),
                                   th.DARK_TOKENS["accent"])
            else:
                n = len(saved)
                self._invoke_toast(
                    f"✓  {n} crop{'s' if n != 1 else ''} saved",
                    "#27ae60")
            self._invoke_status(f"✓ Saved {len(saved)} crops → {sd}")

        threading.Thread(target=worker, daemon=True).start()

    def _invoke_toast(self, msg: str, color: str) -> None:
        QtCore.QMetaObject.invokeMethod(
            self, "_show_toast",
            Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(str, msg),
            QtCore.Q_ARG(str, color))

    def _invoke_status(self, msg: str) -> None:
        QtCore.QMetaObject.invokeMethod(
            self, "_set_status",
            Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(str, msg))

    @QtCore.pyqtSlot(str, str)
    def _show_toast(self, msg: str, color: str) -> None:
        self._toast._reposition()
        self._toast.show_msg(msg, color)

    @QtCore.pyqtSlot(str)
    def _set_status(self, msg: str) -> None:
        self._status(msg)

    # ── drag & drop (catches drops on toolbar / panel areas) ──────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self._try_load(urls[0].toLocalFile())
        e.acceptProposedAction()
