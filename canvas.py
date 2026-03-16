"""
canvas.py — QGraphicsView-based image canvas with draggable selections.

Classes
-------
SelItem  — a single resizable/movable rectangle drawn over the image
Canvas   — the main view; owns the scene, image pixmap, and all SelItems
"""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui  import (QPen, QBrush, QColor, QPixmap, QImage,
                           QFont, QTransform, QCursor)
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsRectItem,
                              QGraphicsItem, QGraphicsTextItem)
from PIL import Image

from models import Sel
import theme as th

EDGE        = 10   # px from rect edge that counts as a resize hit
HANDLE_SIZE = 8    # corner handle square side length


class SelItem(QGraphicsRectItem):
    """
    A draggable, resizable selection rectangle rendered on the scene.

    The item works in scene/image space — coordinates stored in the
    associated Sel object are also image-space, so no conversion is needed
    when reading or writing them.
    """

    def __init__(self, sel: Sel, idx: int, canvas: "Canvas"):
        super().__init__()
        self.sel    = sel
        self.idx    = idx
        self.canvas = canvas

        self._drag_mode   = None   # None | "move" | edge code string
        self._drag_start  = None   # QPointF scene position at drag start
        self._orig        = None   # (ix1, iy1, ix2, iy2) snapshot
        self._duplicating = False  # Alt/Option drag-to-duplicate
        self._dup_ghost   = None   # ghost QGraphicsRectItem during duplicate

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(1)

        self._active  = False
        self._label   = QGraphicsTextItem(self)
        self._label.setFont(QFont("Consolas", 9))
        self._label.setDefaultTextColor(th.C_SEL)

        self._handles: list[QGraphicsRectItem] = []

        self._sync()

    # ── public API ────────────────────────────────────────────────────────────

    def set_active(self, active: bool) -> None:
        self._active = active
        color = th.C_SEL_ACT if active else th.C_SEL
        self.setPen(QPen(color, 2))
        self._label.setDefaultTextColor(color)
        for h in self._handles:
            h.setVisible(active)
        if active:
            self._update_handles()
        self._apply_brush()

    def _apply_brush(self) -> None:
        """Set fill brush based on overlay mode and overlay colour settings."""
        if self.canvas.overlay_mode:
            c = QColor(th.C_OVERLAY)
            c.setAlpha(th.OVERLAY_ALPHA)
            self.setBrush(QBrush(c))
        else:
            self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def ensure_handles(self) -> None:
        """Create corner handle items if they don't exist yet."""
        if not self._handles:
            for _ in range(4):
                h = QGraphicsRectItem(self)
                h.setBrush(QBrush(th.C_HANDLE))
                h.setPen(QPen(th.C_BG, 1))
                h.setZValue(2)
                h.setVisible(False)
                self._handles.append(h)

    def _sync(self) -> None:
        """Recompute all visual properties from self.sel's image-space coords."""
        s = self.sel
        r = QRectF(QPointF(s.ix1, s.iy1), QPointF(s.ix2, s.iy2))
        self.setRect(r)
        self.set_active(self._active)

        display = s.name if s.name else f"#{self.idx + 1}"
        self._label.setPlainText(display)

        # Scale label font so it looks ~14px on screen regardless of zoom
        zoom = max(0.1, self.canvas.zoom)
        pt   = max(7, int(14 / zoom))
        self._label.setFont(QFont("Consolas", pt, QFont.Weight.Bold))
        self._label.setPos(r.topLeft() + QPointF(6 / zoom, 4 / zoom))
        self._apply_brush()
        self._update_handles()

    # ── internals ─────────────────────────────────────────────────────────────

    def _update_handles(self) -> None:
        r  = self.rect()
        hr = HANDLE_SIZE / 2
        corners = [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()]
        for h, c in zip(self._handles, corners):
            h.setRect(QRectF(c.x() - hr, c.y() - hr, HANDLE_SIZE, HANDLE_SIZE))

    def _hit_part(self, pos: QPointF) -> str:
        """Return which part of the rect the cursor is over."""
        r = self.rect()
        x, y = pos.x(), pos.y()
        E   = EDGE
        oL  = abs(x - r.left())   <= E
        oR  = abs(x - r.right())  <= E
        oT  = abs(y - r.top())    <= E
        oB  = abs(y - r.bottom()) <= E
        if oL and oT: return "TL"
        if oR and oT: return "TR"
        if oL and oB: return "BL"
        if oR and oB: return "BR"
        if oL: return "L"
        if oR: return "R"
        if oT: return "T"
        if oB: return "B"
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

    # ── Qt event handlers ─────────────────────────────────────────────────────

    def hoverMoveEvent(self, e):
        part = self._hit_part(e.pos())
        self.setCursor(QCursor(self._CURSORS.get(
            part, Qt.CursorShape.SizeAllCursor)))
        self.canvas.on_sel_hover(self.idx, part)

    def hoverLeaveEvent(self, e):
        self.unsetCursor()
        self.canvas.on_sel_leave()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.canvas.activate_sel(self.idx)
            self._drag_start = e.scenePos()
            self._orig       = self.sel.rect()
            alt = bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)
            if alt and self._hit_part(e.pos()) == "move":
                # Alt+drag — start a duplicate ghost, leave original in place
                self._duplicating = True
                self._drag_mode   = "move"
                x1, y1, x2, y2 = self.sel.rect()
                self._dup_ghost = QGraphicsRectItem(
                    QRectF(QPointF(x1, y1), QPointF(x2, y2)))
                self._dup_ghost.setPen(
                    QPen(th.C_SEL_ACT, 2, Qt.PenStyle.DashLine))
                # Show overlay fill on ghost when overlay mode is active,
                # at half the configured opacity so it reads as a preview
                if self.canvas.overlay_mode:
                    ghost_fill = QColor(th.C_OVERLAY)
                    ghost_fill.setAlpha(max(20, th.OVERLAY_ALPHA // 2))
                    self._dup_ghost.setBrush(QBrush(ghost_fill))
                else:
                    self._dup_ghost.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self._dup_ghost.setZValue(10)
                self.canvas.scene.addItem(self._dup_ghost)
                self.canvas.setCursor(
                    QCursor(Qt.CursorShape.DragCopyCursor))
            else:
                self._duplicating = False
                self._drag_mode   = self._hit_part(e.pos())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_mode is None:
            return
        sp = e.scenePos()
        dx = sp.x() - self._drag_start.x()
        dy = sp.y() - self._drag_start.y()
        x1o, y1o, x2o, y2o = self._orig

        if self._duplicating:
            # Move ghost only — original stays untouched
            if self._dup_ghost:
                self._dup_ghost.setRect(QRectF(
                    QPointF(x1o + dx, y1o + dy),
                    QPointF(x2o + dx, y2o + dy)))
        else:
            s = self.sel
            p = self._drag_mode
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

    def contextMenuEvent(self, e):
        """Right-click context menu for a selection."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #16213e; color: #eaeaea; border: 1px solid #8888aa; "
            "font-family: 'Inter', sans-serif; font-size: 9pt; padding: 4px; }"
            "QMenu::item { padding: 6px 20px; border-radius: 3px; }"
            "QMenu::item:selected { background: #e94560; }"
            "QMenu::separator { height: 1px; background: #8888aa; margin: 3px 8px; }")
        act_dup    = menu.addAction("Duplicate")
        act_dup.setToolTip("Alt+drag")
        menu.addSeparator()
        act_del    = menu.addAction("Delete")
        chosen = menu.exec(e.screenPos())
        if chosen == act_dup:
            # Duplicate in place with a small offset so it's visible
            s = self.sel
            offset = 20
            new_sel = self.canvas.add_sel(
                s.ix1 + offset, s.iy1 + offset,
                s.ix2 + offset, s.iy2 + offset)
            new_sel.name = s.name
            self.canvas.sel_items[-1]._sync()
        elif chosen == act_del:
            self.canvas.delete_sel(self.idx)
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._duplicating and self._dup_ghost:
            r = self._dup_ghost.rect()
            self.canvas.scene.removeItem(self._dup_ghost)
            self._dup_ghost = None
            new_sel = self.canvas.add_sel(
                r.left(), r.top(), r.right(), r.bottom())
            new_sel.name = self.sel.name  # carry name over
            self.canvas.sel_items[-1]._sync()  # refresh label
            self.canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._duplicating = False
        self._drag_mode   = None
        e.accept()


class Canvas(QGraphicsView):
    """
    The main image canvas.

    Responsibilities:
      • Displaying the current PIL image as a QPixmap
      • Hosting SelItem objects that the user draws/moves/resizes
      • Forwarding drag-and-drop file drops to on_load
      • Emitting coord updates to on_coords
      • Zoom and pan

    Callbacks (set by MainWindow after construction):
      on_load(path: str)          — called when a file is dropped
      on_coords(x, y) | (None, None) — cursor image coordinates
      refresh_list()              — called after any selection change
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(self.renderHints().Antialiasing)
        self.setRenderHint(self.renderHints().SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(True)

        # State
        self.overlay_mode: bool = False   # semi-transparent fill on selections
        self.pil_img:   Image.Image | None = None
        self.zoom:      float              = 1.0
        self._pixmap:   QPixmap | None     = None
        self._px_item                      = None
        self.sels:      list[Sel]          = []
        self.sel_items: list[SelItem]      = []
        self.active:    int | None         = None
        self._drawing   = False
        self._draw_start: QPointF | None   = None
        self._rubber:   QGraphicsRectItem | None = None
        self._panning   = False
        self._pan_start = None

        # Callbacks — wire up in MainWindow
        self.on_load:      callable | None = None
        self.on_coords:    callable | None = None
        self.refresh_list: callable        = lambda: None
        self.on_sel_hover: callable        = lambda idx, part: None
        self.on_sel_leave: callable        = lambda: None

    # ── image ─────────────────────────────────────────────────────────────────

    def load_image(self, pil_img: Image.Image) -> None:
        self.pil_img = pil_img
        self.scene.clear()
        self._px_item  = None
        self.sel_items = []
        self._draw_pixmap()
        self.fit()

    def _draw_pixmap(self) -> None:
        if not self.pil_img:
            return
        img  = self.pil_img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        self._pixmap = QPixmap.fromImage(qimg)
        if self._px_item:
            self._px_item.setPixmap(self._pixmap)
        else:
            self._px_item = self.scene.addPixmap(self._pixmap)
            self._px_item.setZValue(0)
        self.scene.setSceneRect(QRectF(self._pixmap.rect()))

    # ── zoom ──────────────────────────────────────────────────────────────────

    def fit(self) -> None:
        if not self._px_item:
            return
        self.fitInView(self._px_item, Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom = self.transform().m11()
        self._redraw_all_sels()

    def set_zoom(self, factor: float) -> None:
        self.zoom = max(0.05, min(8.0, factor))
        t = QTransform()
        t.scale(self.zoom, self.zoom)
        self.setTransform(t)
        self._redraw_all_sels()

    def zoom_in(self):   self.set_zoom(self.zoom * 1.25)
    def zoom_out(self):  self.set_zoom(self.zoom / 1.25)
    def zoom_fit(self):  self.fit()
    def zoom_pct(self):  return int(self.zoom * 100)

    # ── selections ────────────────────────────────────────────────────────────

    def add_sel(self, ix1: float, iy1: float,
                ix2: float, iy2: float) -> Sel:
        """Create a Sel, add it to the scene, and return it."""
        s    = Sel(ix1, iy1, ix2, iy2)
        item = SelItem(s, len(self.sels), self)
        item.ensure_handles()
        self.scene.addItem(item)
        self.sels.append(s)
        self.sel_items.append(item)
        self.activate_sel(len(self.sels) - 1)
        self.refresh_list()
        return s

    def activate_sel(self, idx: int | None) -> None:
        if self.active is not None and self.active < len(self.sel_items):
            self.sel_items[self.active].set_active(False)
        self.active = idx
        if idx is not None and idx < len(self.sel_items):
            self.sel_items[idx].set_active(True)
        self.refresh_list()

    def deactivate(self) -> None:
        self.activate_sel(None)

    def delete_sel(self, idx: int | None) -> None:
        if idx is None or idx >= len(self.sels):
            return
        self.scene.removeItem(self.sel_items[idx])
        self.sels.pop(idx)
        self.sel_items.pop(idx)
        self.active = None
        for i, item in enumerate(self.sel_items):
            item.idx = i
            item._sync()
        self.refresh_list()

    def delete_active(self) -> None:
        self.delete_sel(self.active)

    def delete_last(self) -> None:
        if self.sels:
            self.delete_sel(len(self.sels) - 1)

    def clear_all(self) -> None:
        for item in self.sel_items:
            self.scene.removeItem(item)
        self.sels.clear()
        self.sel_items.clear()
        self.active = None
        self.refresh_list()

    def _redraw_all_sels(self) -> None:
        for item in self.sel_items:
            item._sync()

    def toggle_overlay(self) -> bool:
        """Toggle overlay fill mode. Returns the new state."""
        self.overlay_mode = not self.overlay_mode
        self._redraw_all_sels()
        return self.overlay_mode

    def set_overlay(self, enabled: bool) -> None:
        """Set overlay mode explicitly and redraw."""
        if self.overlay_mode != enabled:
            self.overlay_mode = enabled
            self._redraw_all_sels()

    # ── mouse / keyboard events ───────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return

        sp   = self.mapToScene(e.position().toPoint())
        item = self.scene.itemAt(sp, self.transform())

        # Clicked on existing selection or its handle → let Qt route it
        if isinstance(item, SelItem) or (
                item and item.parentItem() and
                isinstance(item.parentItem(), SelItem)):
            super().mousePressEvent(e)
            return

        # Shift held → pan
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._panning   = True
            self._pan_start = e.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            e.accept()
            return

        # Start drawing a new selection
        if self.pil_img:
            self.deactivate()
            self._drawing    = True
            self._draw_start = sp
            self._rubber     = QGraphicsRectItem()
            self._rubber.setPen(QPen(th.C_SEL_ACT, 2, Qt.PenStyle.DashLine))
            self._rubber.setZValue(10)
            self.scene.addItem(self._rubber)
        e.accept()

    def mouseMoveEvent(self, e):
        sp = self.mapToScene(e.position().toPoint())

        # Update coordinate display
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
            self._panning   = False
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
                    self.add_sel(
                        max(0, min(r.left(),  iw)),
                        max(0, min(r.top(),   ih)),
                        max(0, min(r.right(), iw)),
                        max(0, min(r.bottom(), ih)),
                    )
            e.accept()
            return

        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        if e.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_active()
        else:
            super().keyPressEvent(e)

    def enterEvent(self, e):
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        super().enterEvent(e)

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
