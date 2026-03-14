#!/usr/bin/env python3
"""
Image Splicer — multi-region crop utility (PyQt6)
  • Open via button or Ctrl/Cmd+O
  • Drag & drop an image file onto the window (all platforms)
  • Draw, move, and resize rectangle selections
  • Keep selections when loading a new image (toolbar toggle)
  • One-time save-location — remembered between sessions
"""

import json, os, sys
from pathlib import Path

# ── auto-install dependencies ─────────────────────────────────────────────────
def _install(pkg):
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg,
                           "--break-system-packages", "-q"])

try:
    from PyQt6 import QtWidgets, QtCore, QtGui
    from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer
    from PyQt6.QtGui  import (QPainter, QPen, QBrush, QColor, QPixmap,
                               QImage, QFont, QKeySequence, QShortcut,
                               QTransform, QCursor, QPainterPath)
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                                  QToolBar, QPushButton, QCheckBox, QComboBox,
                                  QLineEdit, QFileDialog, QScrollArea,
                                  QSizePolicy, QHBoxLayout, QVBoxLayout,
                                  QFrame, QListWidget, QListWidgetItem,
                                  QGraphicsView, QGraphicsScene,
                                  QGraphicsRectItem, QGraphicsItem,
                                  QGraphicsTextItem, QStatusBar, QSplitter,
                                  QMessageBox, QStyle)
except ImportError:
    _install("PyQt6")
    from PyQt6 import QtWidgets, QtCore, QtGui
    from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer
    from PyQt6.QtGui  import (QPainter, QPen, QBrush, QColor, QPixmap,
                               QImage, QFont, QKeySequence, QShortcut,
                               QTransform, QCursor, QPainterPath)
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                                  QToolBar, QPushButton, QCheckBox, QComboBox,
                                  QLineEdit, QFileDialog, QScrollArea,
                                  QSizePolicy, QHBoxLayout, QVBoxLayout,
                                  QFrame, QListWidget, QListWidgetItem,
                                  QGraphicsView, QGraphicsScene,
                                  QGraphicsRectItem, QGraphicsItem,
                                  QGraphicsTextItem, QStatusBar, QSplitter,
                                  QMessageBox, QStyle)

try:
    from PIL import Image
except ImportError:
    _install("Pillow")
    from PIL import Image

CONFIG_FILE = Path.home() / ".image_splicer_config.json"

def load_cfg():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}

def save_cfg(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

# ── colours ───────────────────────────────────────────────────────────────────
C_BG      = QColor("#1a1a2e")
C_PANEL   = QColor("#16213e")
C_ACCENT  = QColor("#e94560")
C_ACCENT2 = QColor("#0f3460")
C_GREEN   = QColor("#27ae60")
C_GREY    = QColor("#444466")
C_TEXT    = QColor("#eaeaea")
C_TEXTDIM = QColor("#8888aa")
C_HANDLE  = QColor("#ffd700")
C_SEL     = QColor("#e94560")
C_SEL_ACT = QColor("#ff6b6b")

HANDLE_SIZE = 8

# ── stylesheet ────────────────────────────────────────────────────────────────
def _load_qss():
    """Load style.qss from the same directory as this script."""
    qss_path = Path(__file__).parent / "style.qss"
    if qss_path.exists():
        return qss_path.read_text()
    return ""  # no stylesheet found — app still works, just unstyled

QSS = _load_qss()

# ── selection data ────────────────────────────────────────────────────────────
class Sel:
    """A region stored in image-space pixels (floats)."""
    def __init__(self, ix1, iy1, ix2, iy2):
        self.ix1 = min(ix1, ix2)
        self.iy1 = min(iy1, iy2)
        self.ix2 = max(ix1, ix2)
        self.iy2 = max(iy1, iy2)

    def rect(self):
        return (self.ix1, self.iy1, self.ix2, self.iy2)

    def width(self):  return self.ix2 - self.ix1
    def height(self): return self.iy2 - self.iy1

    def fits_in(self, w, h):
        return self.ix1 >= 0 and self.iy1 >= 0 and self.ix2 <= w and self.iy2 <= h


# ── canvas (QGraphicsView) ────────────────────────────────────────────────────

EDGE = 10   # px from edge to trigger resize handle

class SelItem(QGraphicsRectItem):
    """A draggable/resizable selection rectangle on the scene."""

    HANDLE_POS = ["TL","TR","BL","BR"]

    def __init__(self, sel: Sel, idx: int, canvas: "Canvas"):
        super().__init__()
        self.sel    = sel
        self.idx    = idx
        self.canvas = canvas
        self._drag_mode  = None   # None | "move" | edge code
        self._drag_start = None   # QPointF scene pos
        self._orig       = None   # (ix1,iy1,ix2,iy2) snapshot

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(1)

        self._active = False
        self._label  = QGraphicsTextItem(self)

        font = QFont("Consolas", 9)
        self._label.setFont(font)
        self._label.setDefaultTextColor(C_SEL)

        self._handles = []  # QGraphicsRectItem corners

        self._sync()

    def set_active(self, active: bool):
        self._active = active
        color = C_SEL_ACT if active else C_SEL
        self.setPen(QPen(color, 2))
        self._label.setDefaultTextColor(color)
        for h in self._handles:
            h.setVisible(active)
        if active:
            self._update_handles()

    def _sync(self):
        """Update graphics from self.sel image-space coords."""
        s = self.sel
        scene_rect = self.canvas.img_to_scene(s.ix1, s.iy1, s.ix2, s.iy2)
        self.setRect(scene_rect)
        self.set_active(self._active)
        self._label.setPlainText(f"#{self.idx+1}")
        self._label.setPos(scene_rect.topLeft() + QPointF(4, 2))
        self._update_handles()

    def _update_handles(self):
        r = self.rect()
        corners = [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()]
        hr = HANDLE_SIZE / 2
        for i, h in enumerate(self._handles):
            c = corners[i]
            h.setRect(QRectF(c.x()-hr, c.y()-hr, HANDLE_SIZE, HANDLE_SIZE))

    def ensure_handles(self, scene):
        if not self._handles:
            for _ in range(4):
                h = QGraphicsRectItem(self)
                h.setBrush(QBrush(C_HANDLE))
                h.setPen(QPen(C_BG, 1))
                h.setZValue(2)
                h.setVisible(False)
                self._handles.append(h)

    def _hit_part(self, pos: QPointF):
        r = self.rect()
        x, y = pos.x(), pos.y()
        E = EDGE
        on_l = abs(x - r.left())   <= E
        on_r = abs(x - r.right())  <= E
        on_t = abs(y - r.top())    <= E
        on_b = abs(y - r.bottom()) <= E
        if on_l and on_t: return "TL"
        if on_r and on_t: return "TR"
        if on_l and on_b: return "BL"
        if on_r and on_b: return "BR"
        if on_l: return "L"
        if on_r: return "R"
        if on_t: return "T"
        if on_b: return "B"
        return "move"

    _CURSORS = {
        "move": Qt.CursorShape.SizeAllCursor,
        "TL":   Qt.CursorShape.SizeFDiagCursor,
        "BR":   Qt.CursorShape.SizeFDiagCursor,
        "TR":   Qt.CursorShape.SizeBDiagCursor,
        "BL":   Qt.CursorShape.SizeBDiagCursor,
        "L":    Qt.CursorShape.SizeHorCursor,
        "R":    Qt.CursorShape.SizeHorCursor,
        "T":    Qt.CursorShape.SizeVerCursor,
        "B":    Qt.CursorShape.SizeVerCursor,
    }

    def hoverMoveEvent(self, e):
        part = self._hit_part(e.pos())
        self.setCursor(QCursor(self._CURSORS.get(part, Qt.CursorShape.SizeAllCursor)))

    def hoverLeaveEvent(self, e):
        self.unsetCursor()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.canvas.activate_sel(self.idx)
            self._drag_mode  = self._hit_part(e.pos())
            self._drag_start = e.scenePos()
            self._orig       = self.sel.rect()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_mode is None:
            return
        sp   = e.scenePos()
        dx   = (sp.x() - self._drag_start.x()) / self.canvas.zoom
        dy   = (sp.y() - self._drag_start.y()) / self.canvas.zoom
        x1o, y1o, x2o, y2o = self._orig
        p = self._drag_mode
        s = self.sel
        if   p == "move": s.ix1,s.iy1,s.ix2,s.iy2 = x1o+dx,y1o+dy,x2o+dx,y2o+dy
        elif p == "TL":   s.ix1,s.iy1 = x1o+dx, y1o+dy
        elif p == "TR":   s.ix2,s.iy1 = x2o+dx, y1o+dy
        elif p == "BL":   s.ix1,s.iy2 = x1o+dx, y2o+dy
        elif p == "BR":   s.ix2,s.iy2 = x2o+dx, y2o+dy
        elif p == "L":    s.ix1 = x1o+dx
        elif p == "R":    s.ix2 = x2o+dx
        elif p == "T":    s.iy1 = y1o+dy
        elif p == "B":    s.iy2 = y2o+dy
        self._sync()
        self.canvas.refresh_list()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_mode = None
        e.accept()


class Canvas(QGraphicsView):
    """The main image + selection canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(True)

        self.pil_img    = None
        self.zoom       = 1.0
        self._pixmap    = None
        self._px_item   = None
        self.sels       = []       # list[Sel]
        self.sel_items  = []       # list[SelItem]
        self.active     = None     # int | None
        self._drawing   = False
        self._draw_start = None    # QPointF scene pos
        self._rubber    = None     # QGraphicsRectItem temp rect
        self._panning   = False
        self._pan_start = None

        # Callbacks set by MainWindow
        self.on_load    = None   # callable(path)
        self.on_coords  = None   # callable(x, y) or None
        self.refresh_list = lambda: None

    # ── image ─────────────────────────────────────────────────────────────────

    def load_image(self, pil_img: Image.Image):
        self.pil_img = pil_img
        self.scene.clear()
        self._px_item  = None
        self.sel_items = []
        self._draw_pixmap()
        self.fit()

    def _draw_pixmap(self):
        if not self.pil_img:
            return
        img = self.pil_img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        self._pixmap = QPixmap.fromImage(qimg)
        if self._px_item:
            self._px_item.setPixmap(self._pixmap)
        else:
            self._px_item = self.scene.addPixmap(self._pixmap)
            self._px_item.setZValue(0)
        self.scene.setSceneRect(QRectF(self._pixmap.rect()))

    def fit(self):
        if not self._px_item:
            return
        self.fitInView(self._px_item, Qt.AspectRatioMode.KeepAspectRatio)
        # read back the actual scale Qt applied
        self.zoom = self.transform().m11()
        self._redraw_all_sels()

    def set_zoom(self, factor):
        self.zoom = max(0.05, min(8.0, factor))
        t = QTransform()
        t.scale(self.zoom, self.zoom)
        self.setTransform(t)
        self._redraw_all_sels()

    def zoom_in(self):  self.set_zoom(self.zoom * 1.25)
    def zoom_out(self): self.set_zoom(self.zoom / 1.25)
    def zoom_fit(self): self.fit()
    def zoom_pct(self): return int(self.zoom * 100)

    # ── coordinate helpers ────────────────────────────────────────────────────

    def scene_to_img(self, sx, sy):
        """Scene coords → image pixel coords."""
        return sx, sy   # scene IS image space (pixmap at origin)

    def img_to_scene(self, ix1, iy1, ix2, iy2) -> QRectF:
        return QRectF(QPointF(ix1, iy1), QPointF(ix2, iy2))

    def viewport_to_img(self, vx, vy):
        sp = self.mapToScene(int(vx), int(vy))
        return sp.x(), sp.y()

    # ── selections ────────────────────────────────────────────────────────────

    def add_sel_image_space(self, ix1, iy1, ix2, iy2):
        s = Sel(ix1, iy1, ix2, iy2)
        self.sels.append(s)
        item = SelItem(s, len(self.sels)-1, self)
        item.ensure_handles(self.scene)
        self.scene.addItem(item)
        self.sel_items.append(item)
        self.activate_sel(len(self.sels)-1)
        self.refresh_list()
        return s

    def activate_sel(self, idx):
        if self.active is not None and self.active < len(self.sel_items):
            self.sel_items[self.active].set_active(False)
        self.active = idx
        if idx is not None and idx < len(self.sel_items):
            self.sel_items[idx].set_active(True)
        self.refresh_list()

    def deactivate(self):
        self.activate_sel(None)

    def delete_sel(self, idx):
        if idx is None or idx >= len(self.sels):
            return
        self.scene.removeItem(self.sel_items[idx])
        self.sels.pop(idx)
        self.sel_items.pop(idx)
        self.active = None
        # renumber remaining items
        for i, item in enumerate(self.sel_items):
            item.idx = i
            item._label.setPlainText(f"#{i+1}")
        self.refresh_list()

    def delete_active(self):
        self.delete_sel(self.active)

    def delete_last(self):
        if self.sels:
            self.delete_sel(len(self.sels)-1)

    def clear_all(self):
        for item in self.sel_items:
            self.scene.removeItem(item)
        self.sels.clear()
        self.sel_items.clear()
        self.active = None
        self.refresh_list()

    def _redraw_all_sels(self):
        for item in self.sel_items:
            item._sync()

    # ── drawing new selections ────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(e.position().toPoint())
            # Check if clicking on existing selection item
            item = self.scene.itemAt(sp, self.transform())
            if isinstance(item, SelItem) or (item and item.parentItem() and isinstance(item.parentItem(), SelItem)):
                super().mousePressEvent(e)
                return
            # Check if shift held — pan
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._panning  = True
                self._pan_start = e.position()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                e.accept()
                return
            # Start drawing new selection
            if self.pil_img:
                self.deactivate()
                self._drawing    = True
                self._draw_start = sp
                self._rubber     = QGraphicsRectItem()
                self._rubber.setPen(QPen(C_SEL_ACT, 2, Qt.PenStyle.DashLine))
                self._rubber.setZValue(10)
                self.scene.addItem(self._rubber)
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # update coord display
        sp = self.mapToScene(e.position().toPoint())
        if self.on_coords and self.pil_img:
            x, y = int(sp.x()), int(sp.y())
            iw, ih = self.pil_img.size
            if 0 <= x <= iw and 0 <= y <= ih:
                self.on_coords(x, y)
            else:
                self.on_coords(None, None)

        if self._panning and self._pan_start is not None:
            delta = e.position() - self._pan_start
            self._pan_start = e.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            e.accept()
            return

        if self._drawing and self._rubber:
            sp2 = self.mapToScene(e.position().toPoint())
            self._rubber.setRect(QRectF(self._draw_start, sp2).normalized())
            e.accept()
            return

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            e.accept()
            return

        if self._drawing:
            self._drawing = False
            if self._rubber:
                r = self._rubber.rect()
                self.scene.removeItem(self._rubber)
                self._rubber = None
                if r.width() > 4 and r.height() > 4 and self.pil_img:
                    iw, ih = self.pil_img.size
                    ix1 = max(0, min(r.left(),   iw))
                    iy1 = max(0, min(r.top(),    ih))
                    ix2 = max(0, min(r.right(),  iw))
                    iy2 = max(0, min(r.bottom(), ih))
                    self.add_sel_image_space(ix1, iy1, ix2, iy2)
            e.accept()
            return

        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_active()
        else:
            super().keyPressEvent(e)

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls and self.on_load:
            path = urls[0].toLocalFile()
            if path:
                self.on_load(path)
        e.acceptProposedAction()

    def enterEvent(self, e):
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        super().enterEvent(e)


# ── toast overlay ─────────────────────────────────────────────────────────────

class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background: #27ae60;
                color: #eaeaea;
                border-radius: 6px;
                padding: 10px 20px;
                font-family: Consolas, monospace;
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        self.hide()
        self._timer  = QTimer(self)
        self._fade_t = QTimer(self)
        self._alpha  = 1.0
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade)
        self._fade_t.setInterval(30)
        self._fade_t.timeout.connect(self._fade_step)

    def show_msg(self, msg, color="#27ae60", duration=2200):
        self._alpha = 1.0
        self._fade_t.stop()
        self.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: #eaeaea;
                border-radius: 6px;
                padding: 10px 20px;
                font-family: Consolas, monospace;
                font-size: 11pt;
                font-weight: bold;
            }}
        """)
        self.setText(msg)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(duration)

    def _reposition(self):
        if self.parent():
            pw = self.parent().width()
            self.move((pw - self.width()) // 2, 60)

    def resizeEvent(self, e):
        self._reposition()

    def _start_fade(self):
        self._fade_t.start()

    def _fade_step(self):
        self._alpha -= 0.05
        if self._alpha <= 0:
            self._fade_t.stop()
            self.hide()
            return
        op = max(0.0, self._alpha)
        self.setWindowOpacity(op)
        # blend bg color toward canvas bg
        self.setStyleSheet(self.styleSheet())   # trigger repaint


# ── side panel ────────────────────────────────────────────────────────────────

class SidePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setStyleSheet("background: #16213e;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(6)

        title = QLabel("SELECTIONS")
        title.setStyleSheet("color: #e94560; font-size: 13pt; font-weight: bold;"
                            "font-family: Consolas, monospace;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e94560;")
        lay.addWidget(sep)

        self.list_widget = QListWidget()
        lay.addWidget(self.list_widget, stretch=1)

        # prefix
        lay.addWidget(self._lbl("Filename prefix:"))
        self.prefix_edit = QLineEdit("crop")
        lay.addWidget(self.prefix_edit)

        # format
        lay.addWidget(self._lbl("Format:"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["PNG", "JPEG", "WEBP", "BMP", "TIFF"])
        lay.addWidget(self.fmt_combo)

    @staticmethod
    def _lbl(text):
        l = QLabel(text)
        l.setObjectName("dimmed")
        return l

    def refresh(self, sels, active_idx, on_delete):
        self.list_widget.clear()
        for i, s in enumerate(sels):
            w = abs(int(s.ix2 - s.ix1))
            h = abs(int(s.iy2 - s.iy1))
            item = QListWidgetItem(f"#{i+1}   {w}×{h}px")
            self.list_widget.addItem(item)
            if i == active_idx:
                item.setSelected(True)


# ── toolbar button helper ─────────────────────────────────────────────────────

def tb_btn(text, tooltip, style_id, parent=None):
    b = QPushButton(text, parent)
    b.setObjectName(style_id)
    b.setToolTip(tooltip)
    return b


# ── main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Splicer")
        self.setMinimumSize(1100, 600)
        self.cfg = load_cfg()

        import platform
        self._mac = platform.system() == "Darwin"
        self._mod = "Cmd" if self._mac else "Ctrl"

        self._build_ui()
        self._build_shortcuts()
        self.statusBar().showMessage(
            "Open an image to get started — or drag & drop a file onto the window.")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Central widget
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Canvas must exist before toolbar so button signals can connect
        self.canvas = Canvas()
        self.canvas.on_load      = self._try_load
        self.canvas.on_coords    = self._update_coords
        self.canvas.refresh_list = self._refresh_list

        # Toolbar
        tb = self._build_toolbar()
        root_lay.addWidget(tb)

        # Splitter: canvas | side panel
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self.canvas)

        self.side = SidePanel()
        self.side.list_widget.itemClicked.connect(self._list_clicked)
        self.side.prefix_edit.setText(self.cfg.get("prefix", "crop"))
        self.side.prefix_edit.textChanged.connect(
            lambda t: self._persist("prefix", t))
        self.side.fmt_combo.setCurrentText(self.cfg.get("format", "PNG"))
        self.side.fmt_combo.currentTextChanged.connect(
            lambda t: self._persist("format", t))
        splitter.addWidget(self.side)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root_lay.addWidget(splitter, stretch=1)

        # Status bar
        self.setStatusBar(QStatusBar())
        self._coord_lbl = QLabel("")
        self._coord_lbl.setObjectName("dimmed")
        self.statusBar().addPermanentWidget(self._coord_lbl)

        # Toast
        self._toast = Toast(self.canvas)

    def _build_toolbar(self):
        tb = QWidget()
        tb.setStyleSheet("background: #16213e;")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        def sep():
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setStyleSheet("color: #e94560;")
            return f

        m = self._mod
        self._btn_open  = tb_btn("⊞  Open Image",    f"Open image ({m}+O)", "accent")
        self._btn_save_loc = tb_btn("⌂  Save Location", "", "")
        self._btn_save  = tb_btn("✦  Save Crops",    f"Save all crops ({m}+S)", "green")
        self._btn_del   = tb_btn("⌫  Delete Sel",    "Delete selected  (Delete / Backspace)", "grey")
        self._btn_clear = tb_btn("✕  Clear All",     "Clear all selections", "grey")
        self.keep_chk   = QCheckBox("Keep selections")
        self.keep_chk.setToolTip("Keep selections when loading a new image")
        self.keep_chk.setChecked(self.cfg.get("keep_sels", True))
        self.keep_chk.stateChanged.connect(
            lambda: self._persist("keep_sels", self.keep_chk.isChecked()))

        self._btn_fit   = tb_btn("⊡", f"Fit image to window  ({m}+0)", "")
        self._btn_zin   = tb_btn("+", f"Zoom in  ({m}+=)", "")
        self._btn_zout  = tb_btn("−", f"Zoom out  ({m}+−)", "")
        for b in (self._btn_fit, self._btn_zin, self._btn_zout):
            b.setFixedWidth(38)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFixedWidth(48)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._update_save_tip()

        for w in (self._btn_open, self._btn_save_loc, self._btn_save,
                  sep(), self._btn_del, self._btn_clear,
                  sep(), self.keep_chk):
            lay.addWidget(w)

        lay.addStretch()

        zoom_lbl = QLabel("Zoom:")
        zoom_lbl.setObjectName("dimmed")
        for w in (zoom_lbl, self._zoom_lbl,
                  self._btn_fit, self._btn_zin, self._btn_zout):
            lay.addWidget(w)

        # connect
        self._btn_open.clicked.connect(self._open_file)
        self._btn_save_loc.clicked.connect(self._set_save)
        self._btn_save.clicked.connect(self._save_crops)
        self._btn_del.clicked.connect(self.canvas.delete_active)
        self._btn_clear.clicked.connect(self.canvas.clear_all)
        self._btn_fit.clicked.connect(self._zoom_fit)
        self._btn_zin.clicked.connect(self._zoom_in)
        self._btn_zout.clicked.connect(self._zoom_out)

        return tb

    def _build_shortcuts(self):
        m = "Meta" if self._mac else "Ctrl"

        def sc(key, fn):
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        sc(f"{m}+O",     self._open_file)
        sc(f"{m}+S",     self._save_crops)
        sc(f"{m}+Z",     self.canvas.delete_last)
        sc(f"{m}+=",     self._zoom_in)
        sc(f"{m}++",     self._zoom_in)
        sc(f"{m}+-",     self._zoom_out)
        sc(f"{m}+0",     self._zoom_fit)
        sc("Delete",     self.canvas.delete_active)
        sc("Backspace",  self.canvas.delete_active)
        sc("Escape",     self._cancel_draw)

    # ── zoom ──────────────────────────────────────────────────────────────────

    def _zoom_in(self):
        self.canvas.zoom_in()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _zoom_out(self):
        self.canvas.zoom_out()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _zoom_fit(self):
        self.canvas.zoom_fit()
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _cancel_draw(self):
        if self.canvas._drawing and self.canvas._rubber:
            self.canvas.scene.removeItem(self.canvas._rubber)
            self.canvas._rubber   = None
            self.canvas._drawing  = False

    # ── status helpers ────────────────────────────────────────────────────────

    def _update_coords(self, x, y):
        if x is None:
            self._coord_lbl.setText("")
        else:
            self._coord_lbl.setText(f"x:{x}  y:{y}")

    def _status(self, msg):
        self.statusBar().showMessage(msg)

    def _update_save_tip(self):
        sd = self.cfg.get("save_dir", "(not set)")
        self._btn_save_loc.setToolTip(f"Save location: {sd}")

    # ── side list ─────────────────────────────────────────────────────────────

    def _refresh_list(self):
        self.side.refresh(self.canvas.sels, self.canvas.active,
                          self.canvas.delete_sel)
        n = len(self.canvas.sels)
        active = self.canvas.active
        if active is not None and active < len(self.canvas.sels):
            s = self.canvas.sels[active]
            w, h = int(s.width()), int(s.height())
            self._status(f"Selection #{active+1} — {w}×{h}px   |   {n} total")
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    def _list_clicked(self, item):
        row = self.side.list_widget.row(item)
        self.canvas.activate_sel(row)

    # ── file handling ─────────────────────────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif);;All Files (*)")
        if path:
            self._try_load(path)

    def _try_load(self, path):
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

        # decide what to do with existing selections
        restore = []
        if self.canvas.sels and self.canvas.pil_img and self.keep_chk.isChecked():
            for s in self.canvas.sels:
                if s.fits_in(new_img.width, new_img.height):
                    restore.append(s.rect())

        self.canvas.clear_all()
        self.canvas.load_image(new_img)

        for (ix1, iy1, ix2, iy2) in restore:
            self.canvas.add_sel_image_space(ix1, iy1, ix2, iy2)
        self.canvas.deactivate()
        self._refresh_list()

        self.setWindowTitle(f"Image Splicer — {Path(path).name}")
        extra = f"  — kept {len(restore)} selection(s)" if restore else ""
        self._status(
            f"Loaded: {Path(path).name}  ({new_img.width}×{new_img.height}px){extra}")
        self._zoom_lbl.setText(f"{self.canvas.zoom_pct()}%")

    # ── save ──────────────────────────────────────────────────────────────────

    def _set_save(self):
        d = QFileDialog.getExistingDirectory(self, "Choose save folder")
        if d:
            self.cfg["save_dir"] = d
            save_cfg(self.cfg)
            self._update_save_tip()
            self._status(f"Save location: {d}")

    def _persist(self, key, val):
        self.cfg[key] = val
        save_cfg(self.cfg)

    def _save_crops(self):
        if not self.canvas.pil_img:
            QMessageBox.warning(self, "No Image", "Open an image first.")
            return
        if not self.canvas.sels:
            QMessageBox.warning(self, "No Selections", "Draw at least one selection.")
            return
        sd = self.cfg.get("save_dir", "")
        if not sd or not os.path.isdir(sd):
            QMessageBox.warning(self, "No Save Location",
                "Set a save location first (Save Location button).")
            return

        import threading
        def worker():
            prefix = self.side.prefix_edit.text() or "crop"
            fmt    = self.side.fmt_combo.currentText()
            ext    = "jpg" if fmt == "JPEG" else fmt.lower()
            saved, errors = [], []
            for i, s in enumerate(self.canvas.sels):
                ix1,iy1,ix2,iy2 = (max(0,int(s.ix1)), max(0,int(s.iy1)),
                                    min(self.canvas.pil_img.width,  int(s.ix2)),
                                    min(self.canvas.pil_img.height, int(s.iy2)))
                if ix2 <= ix1 or iy2 <= iy1:
                    errors.append(f"#{i+1}: zero-size crop")
                    continue
                crop  = self.canvas.pil_img.crop((ix1, iy1, ix2, iy2))
                base  = f"{prefix}_{i+1:02d}"
                fname = f"{base}.{ext}"; n = 1
                while os.path.exists(os.path.join(sd, fname)):
                    fname = f"{base}_{n}.{ext}"; n += 1
                try:
                    crop.save(os.path.join(sd, fname), fmt,
                              **({"quality": 95} if fmt == "JPEG" else {}))
                    saved.append(fname)
                except Exception as e:
                    errors.append(f"#{i+1}: {e}")

            if errors:
                msg = "\n".join(errors)
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_toast",
                    Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f"⚠ {msg}"),
                    QtCore.Q_ARG(str, "#e94560"))
            else:
                n = len(saved)
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_toast",
                    Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f"✓  {n} crop{'s' if n!=1 else ''} saved"),
                    QtCore.Q_ARG(str, "#27ae60"))
            QtCore.QMetaObject.invokeMethod(
                self, "_set_status",
                Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"✓ Saved {len(saved)} crops → {sd}"))

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.pyqtSlot(str, str)
    def _show_toast(self, msg, color):
        self._toast._reposition()
        self._toast.show_msg(msg, color)

    @QtCore.pyqtSlot(str)
    def _set_status(self, msg):
        self._status(msg)

    # ── drag & drop on main window ────────────────────────────────────────────
    # (canvas handles drops too, but this catches drops on the toolbar/panel)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self._try_load(urls[0].toLocalFile())
        e.acceptProposedAction()


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Fusion style ensures QPushButton backgrounds are respected on all platforms,
    # including macOS which otherwise overrides button colours with native Aqua look.
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
