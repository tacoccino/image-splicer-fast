"""
panels.py — non-dialog UI panels and overlay widgets.

Classes
-------
Toast      — transient fade-out notification overlay
SelRow     — one row in the selections list (badge + name + size)
SidePanel  — right-hand panel containing the selections list and options
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QApplication, QLabel, QWidget, QFrame,
                              QHBoxLayout, QVBoxLayout, QLineEdit,
                              QCheckBox, QScrollArea, QPushButton)

from models import Sel
import theme as th


class Toast(QLabel):
    """
    A brief non-blocking status overlay shown on top of the canvas.

    Usage:
        toast = Toast(canvas_widget)
        toast.show_msg("✓ 3 crops saved", color="#27ae60")
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

        self._timer  = QTimer(self)
        self._fade_t = QTimer(self)
        self._alpha  = 1.0
        self._color  = "#27ae60"

        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade)
        self._fade_t.setInterval(30)
        self._fade_t.timeout.connect(self._fade_step)

    def show_msg(self, msg: str, color: str = "#27ae60",
                 duration: int = 2200) -> None:
        self._alpha = 1.0
        self._color = color
        self._fade_t.stop()
        self._apply_style(1.0)
        self.setText(msg)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(duration)

    def _reposition(self) -> None:
        if self.parent():
            pw = self.parent().width()
            self.move((pw - self.width()) // 2, 60)

    def resizeEvent(self, e):
        self._reposition()

    def _apply_style(self, alpha: float) -> None:
        # Interpolate text alpha for the fade effect
        a = max(0, min(255, int(alpha * 255)))
        self.setStyleSheet(
            f"QLabel {{"
            f"  background: {self._color};"
            f"  color: rgba(234,234,234,{a});"
            f"  border-radius: 6px;"
            f"  padding: 10px 20px;"
            f"  font-family: Consolas, monospace;"
            f"  font-size: 11pt;"
            f"  font-weight: bold;"
            f"}}"
        )

    def _start_fade(self):
        self._fade_t.start()

    def _fade_step(self):
        self._alpha -= 0.05
        if self._alpha <= 0:
            self._fade_t.stop()
            self.hide()
            return
        self._apply_style(self._alpha)


class SelRow(QWidget):
    """
    One row in the selections list.

    Layout:  [#n badge] [editable name field] [WxH size label]
    """

    def __init__(self, sel: Sel, idx: int,
                 on_name_change: callable,
                 on_click: callable = lambda i, shift: None,
                 parent=None):
        super().__init__(parent)
        self.sel = sel

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(6)

        # Index badge — clickable to select/add to selection
        self._badge = QPushButton(f"#{idx + 1}")
        self._badge.setObjectName("sel_badge_btn")
        self._badge.setFixedSize(26, 26)
        self._badge.setToolTip(
            "Click to select  ·  Shift+click to add to selection")
        self._badge.clicked.connect(
            lambda checked, i=idx, fn=on_click: fn(
                i,
                bool(QApplication.keyboardModifiers()
                     & Qt.KeyboardModifier.ShiftModifier)))
        lay.addWidget(self._badge)

        # Editable name
        self._name_edit = QLineEdit(sel.name)
        self._name_edit.setPlaceholderText(f"#{idx + 1}")
        self._name_edit.setToolTip("Name this selection (used in saved filename)")
        self._name_edit.textChanged.connect(
            lambda t, s=sel, fn=on_name_change: self._on_text(t, s, fn))
        lay.addWidget(self._name_edit, stretch=1)

        # Size display
        self._size_lbl = QLabel(self._size_str(sel))
        self._size_lbl.setObjectName("dimmed")
        self._size_lbl.setFixedWidth(66)
        self._size_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._size_lbl)

    @staticmethod
    def _size_str(sel: Sel) -> str:
        return f"{abs(int(sel.ix2 - sel.ix1))}×{abs(int(sel.iy2 - sel.iy1))}"

    def _on_text(self, text: str, sel: Sel, callback: callable) -> None:
        sel.name = text.strip()
        callback()

    def update_size(self, sel: Sel) -> None:
        self._size_lbl.setText(self._size_str(sel))

    def set_active(self, active: bool) -> None:
        # Read live resolved colours so this works in both themes
        bg = th.CURRENT_TOKENS["surface_hi"] if active else "transparent"
        fg = th.CURRENT_TOKENS["text"]
        self.setStyleSheet(
            f"QWidget {{ background: {bg}; border-radius: 3px; }}"
            f"QLabel  {{ color: {fg}; }}"
            f"QLineEdit {{ color: {fg}; }}")


class SidePanel(QWidget):
    """
    The right-hand selections panel.

    Contains:
      • A scrollable list of SelRow widgets
      • A filename prefix text field
      • A 'keep selections' checkbox
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(160)
        self.setObjectName("sidepanel")

        self._rows: list[SelRow]  = []
        self._name_change_cb: callable = lambda: None
        self._row_click_cb: callable   = lambda i, shift: None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(6)

        # Title
        title = QLabel("SELECTIONS")
        title.setObjectName("panel_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        lay.addWidget(self._hsep())

        # Scrollable rows
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._container.setObjectName("sidepanel")
        self._list_lay = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, stretch=1)

        lay.addWidget(self._hsep())

        # Prefix field
        prefix_lbl = QLabel("Filename prefix:")
        prefix_lbl.setObjectName("dimmed")
        lay.addWidget(prefix_lbl)

        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("crop")
        self.prefix_edit.setToolTip("Prefix for saved filenames: prefix_name.ext")
        lay.addWidget(self.prefix_edit)

        # Keep-selections checkbox
        self.keep_chk = QCheckBox("Keep selections")
        self.keep_chk.setToolTip(
            "When loading a new image, keep selections that fit inside it")
        lay.addWidget(self.keep_chk)

    @staticmethod
    def _hsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setObjectName("accent_sep")
        return f

    # ── public API ────────────────────────────────────────────────────────────

    def set_name_change_callback(self, fn: callable) -> None:
        """Called whenever the user edits a selection name."""
        self._name_change_cb = fn

    def set_row_click_callback(self, fn: callable) -> None:
        """Called when a badge is clicked: fn(idx, shift_held)."""
        self._row_click_cb = fn

    def refresh(self, sels: list[Sel],
                active_idx: int | None,
                on_delete: callable,
                active_set: set | None = None) -> None:
        """Rebuild the row list to match the current set of selections."""
        if active_set is None:
            active_set = {active_idx} if active_idx is not None else set()
        for row in self._rows:
            self._list_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for i, s in enumerate(sels):
            row = SelRow(s, i, self._name_change_cb,
                         on_click=self._row_click_cb)
            row.set_active(i in active_set)
            self._list_lay.insertWidget(i, row)
            self._rows.append(row)

        # Update size labels for all active rows
        for i in active_set:
            if i < len(self._rows):
                self._rows[i].update_size(sels[i])
