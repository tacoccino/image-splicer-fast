"""
dialogs.py — application dialogs.

Classes
-------
SettingsDialog  — modal settings window (save location, format, theme, accent)
"""

from PyQt6 import QtWidgets
from PyQt6.QtGui import QColor
import theme as th
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QComboBox, QWidget,
                              QFileDialog, QSlider)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    Modal settings dialog.

    On accept, the updated config dict is available as self.result_cfg.
    The caller is responsible for persisting it via config.save_cfg().
    """

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.result_cfg = dict(cfg)   # copy mutated on accept

        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 20, 24, 20)

        # ── Save location ──────────────────────────────────────────────────
        lay.addWidget(self._section("Save Location"))
        loc_row = QHBoxLayout()
        self._save_edit = QLineEdit(cfg.get("save_dir", ""))
        self._save_edit.setPlaceholderText("Choose a folder…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("grey")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        loc_row.addWidget(self._save_edit)
        loc_row.addWidget(browse_btn)
        lay.addLayout(loc_row)

        # ── Output format ──────────────────────────────────────────────────
        lay.addWidget(self._section("Output Format"))
        fmt_row = QHBoxLayout()
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["PNG", "JPEG", "WEBP", "BMP", "TIFF"])
        self._fmt_combo.setCurrentText(cfg.get("format", "PNG"))
        self._fmt_combo.currentTextChanged.connect(self._on_fmt_change)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        lay.addLayout(fmt_row)

        # JPEG quality (shown only when JPEG is selected)
        self._jpeg_row = QWidget()
        jpeg_lay = QHBoxLayout(self._jpeg_row)
        jpeg_lay.setContentsMargins(0, 0, 0, 0)
        jpeg_lay.addWidget(QLabel("JPEG quality:"))
        self._quality_spin = QtWidgets.QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(cfg.get("jpeg_quality", 90))
        self._quality_spin.setFixedWidth(70)
        jpeg_lay.addWidget(self._quality_spin)
        jpeg_lay.addStretch()
        lay.addWidget(self._jpeg_row)
        self._on_fmt_change(self._fmt_combo.currentText())

        # ── Theme ──────────────────────────────────────────────────────────
        lay.addWidget(self._section("Theme"))
        theme_row = QHBoxLayout()
        self._theme_combo = QComboBox()
        available = th.list_themes()
        self._theme_names = [name for name, _ in available]
        self._theme_combo.addItems(self._theme_names)
        # Match saved theme name; normalise legacy 'dark'/'light' values
        saved = cfg.get("theme", "Dark")
        if saved == "dark": saved = "Dark"
        if saved == "light": saved = "Light"
        if saved in self._theme_names:
            self._theme_combo.setCurrentText(saved)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        lay.addLayout(theme_row)
        themes_row = QHBoxLayout()
        hint = QLabel("Add .json files to the themes/ folder to create custom themes")
        hint.setObjectName("dimmed")
        hint.setWordWrap(True)
        themes_row.addWidget(hint, stretch=1)
        open_themes_btn = QPushButton("Open Themes Folder")
        open_themes_btn.setObjectName("grey")
        open_themes_btn.clicked.connect(self._open_themes_folder)
        themes_row.addWidget(open_themes_btn)
        lay.addLayout(themes_row)

        # ── Font scale ────────────────────────────────────────────────────
        lay.addWidget(self._section("Font Scale"))
        scale_row = QHBoxLayout()
        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(80, 160)   # 0.8× to 1.6×
        self._scale_slider.setSingleStep(10)   # snap to 0.1 increments
        self._scale_slider.setPageStep(10)
        self._scale_slider.setValue(
            round(cfg.get("font_scale", 1.0) * 10) * 10)  # snap on load
        self._scale_slider.setTickInterval(10)
        self._scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._scale_lbl = QLabel(
            f"{cfg.get('font_scale', 1.0):.1f}×")
        self._scale_lbl.setFixedWidth(36)
        self._scale_lbl.setObjectName("dimmed")
        # Snap to nearest 10 on release so drag always lands on a tick
        self._scale_slider.valueChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self._scale_slider)
        scale_row.addWidget(self._scale_lbl)
        lay.addLayout(scale_row)

        # ── Zoom speed ────────────────────────────────────────────────────
        lay.addWidget(self._section("Zoom Speed"))
        zoom_row = QHBoxLayout()
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(10, 300)    # 0.1× to 3.0×
        self._zoom_slider.setSingleStep(10)
        self._zoom_slider.setPageStep(10)
        self._zoom_slider.setValue(
            round(cfg.get("zoom_speed", 1.0) * 100))
        self._zoom_slider.setTickInterval(50)
        self._zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._zoom_speed_lbl = QLabel(
            f"{cfg.get('zoom_speed', 1.0):.1f}×")
        self._zoom_speed_lbl.setFixedWidth(36)
        self._zoom_speed_lbl.setObjectName("dimmed")
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zoom_row.addWidget(self._zoom_slider)
        zoom_row.addWidget(self._zoom_speed_lbl)
        lay.addLayout(zoom_row)

        # ── Accent colour ──────────────────────────────────────────────────
        lay.addWidget(self._section("Accent Colour"))
        accent_row = QHBoxLayout()
        self._accent_color = cfg.get("accent", "#e94560")
        self._accent_swatch = QPushButton()
        self._accent_swatch.setFixedSize(32, 32)
        self._accent_swatch.setObjectName("accent_swatch")
        self._update_swatch(self._accent_swatch, self._accent_color)
        self._accent_swatch.clicked.connect(self._pick_accent)
        self._accent_lbl = QLabel(self._accent_color)
        self._accent_lbl.setObjectName("dimmed")
        accent_row.addWidget(self._accent_swatch)
        accent_row.addWidget(self._accent_lbl)
        accent_row.addStretch()
        lay.addLayout(accent_row)

        # ── Overlay fill ──────────────────────────────────────────────────
        lay.addWidget(self._section("Selection Overlay"))
        overlay_row = QHBoxLayout()
        self._overlay_color = cfg.get("overlay_color", "#ff0000")
        self._overlay_swatch = QPushButton()
        self._overlay_swatch.setFixedSize(32, 32)
        self._overlay_swatch.setObjectName("accent_swatch")
        self._update_swatch(self._overlay_swatch, self._overlay_color)
        self._overlay_swatch.clicked.connect(self._pick_overlay)
        self._overlay_color_lbl = QLabel(self._overlay_color)
        self._overlay_color_lbl.setObjectName("dimmed")
        overlay_row.addWidget(self._overlay_swatch)
        overlay_row.addWidget(self._overlay_color_lbl)
        overlay_row.addSpacing(16)
        overlay_row.addWidget(QLabel("Opacity:"))
        self._overlay_spin = QtWidgets.QSpinBox()
        self._overlay_spin.setRange(0, 100)
        self._overlay_spin.setValue(cfg.get("overlay_opacity", 30))
        self._overlay_spin.setFixedWidth(70)
        self._overlay_spin.setSuffix("%")
        overlay_row.addWidget(self._overlay_spin)
        overlay_row.addStretch()
        lay.addLayout(overlay_row)

        # ── OK / Cancel ────────────────────────────────────────────────────
        lay.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("dialog_cancel")
        ok_btn = QPushButton("Save")
        ok_btn.setObjectName("dialog_ok")
        ok_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _section(text: str) -> QLabel:
        """Styled section heading label."""
        lbl = QLabel(text)
        lbl.setObjectName("section_heading")
        return lbl

    def _on_fmt_change(self, fmt: str) -> None:
        self._jpeg_row.setVisible(fmt == "JPEG")

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose save folder")
        if d:
            self._save_edit.setText(d)

    def _pick_accent(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            QColor(self._accent_color), self, "Choose Accent Colour")
        if color.isValid():
            self._accent_color = color.name()
            self._accent_lbl.setText(self._accent_color)
            self._update_swatch(self._accent_swatch, self._accent_color)

    @staticmethod
    def _update_swatch(btn: QPushButton, color: str) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}; border-radius: 4px;"
            f" border: 1px solid rgba(255,255,255,0.2); }}"
            f"QPushButton:hover {{ background: {color}; }}")

    def _pick_overlay(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            QColor(self._overlay_color), self, "Choose Overlay Colour")
        if color.isValid():
            self._overlay_color = color.name()
            self._overlay_color_lbl.setText(self._overlay_color)
            self._update_swatch(self._overlay_swatch, self._overlay_color)

    def _on_zoom_changed(self, v: int) -> None:
        snapped = round(v / 10) * 10
        if snapped != v:
            self._zoom_slider.blockSignals(True)
            self._zoom_slider.setValue(snapped)
            self._zoom_slider.blockSignals(False)
        self._zoom_speed_lbl.setText(f"{snapped / 100:.1f}×")

    def _on_scale_changed(self, v: int) -> None:
        snapped = round(v / 10) * 10
        if snapped != v:
            self._scale_slider.blockSignals(True)
            self._scale_slider.setValue(snapped)
            self._scale_slider.blockSignals(False)
        self._scale_lbl.setText(f"{snapped / 100:.1f}×")

    def _open_themes_folder(self) -> None:
        import os
        from PyQt6 import QtCore, QtGui
        folder = th.themes_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(folder)))

    def _accept(self) -> None:
        self.result_cfg["save_dir"]     = self._save_edit.text().strip()
        self.result_cfg["format"]       = self._fmt_combo.currentText()
        self.result_cfg["jpeg_quality"] = self._quality_spin.value()
        self.result_cfg["theme"]        = self._theme_combo.currentText()
        self.result_cfg["accent"]          = self._accent_color
        self.result_cfg["font_scale"]       = self._scale_slider.value() / 100
        self.result_cfg["overlay_color"]   = self._overlay_color
        self.result_cfg["overlay_opacity"] = self._overlay_spin.value()
        self.result_cfg["zoom_speed"]       = self._zoom_slider.value() / 100
        self.accept()
