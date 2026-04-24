"""
AdaptivePanel — Phase 4 UI tab added to SettingsWindow.

Shows:
  - Per-gesture stats: fire count, misfire rate, adapted values
  - Enable / Disable toggle
  - Reset button to wipe all learning
  - Live refresh every 5 seconds
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QCheckBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class AdaptivePanel(QWidget):

    def __init__(self, adaptive_engine=None, parent=None):
        super().__init__(parent)
        self._engine = adaptive_engine
        self._build_ui()

        # Refresh stats every 5 seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)

    def set_engine(self, engine):
        self._engine = engine
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header row
        header = QHBoxLayout()

        title = QLabel("Adaptive Sensitivity")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))

        self._enable_check = QCheckBox("Enabled")
        self._enable_check.setChecked(True)
        self._enable_check.toggled.connect(self._toggle_enabled)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._enable_check)
        layout.addLayout(header)

        # Description
        desc = QLabel(
            "Wavly watches your gestures and automatically adjusts sensitivity "
            "over time. Misfiring gestures get a higher hold threshold; "
            "reliable ones get faster response."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(desc)

        # Stats area
        stats_lbl = QLabel("PER-GESTURE LEARNING")
        stats_lbl.setStyleSheet("color:#aaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(stats_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        self._stats_container = QWidget()
        self._stats_layout    = QVBoxLayout(self._stats_container)
        self._stats_layout.setContentsMargins(0, 0, 0, 0)
        self._stats_layout.setSpacing(6)
        self._stats_layout.addStretch()

        scroll.setWidget(self._stats_container)
        layout.addWidget(scroll, 1)

        # Bottom row
        bottom = QHBoxLayout()

        self._status_lbl = QLabel("Watching gestures...")
        self._status_lbl.setStyleSheet("color:#aaa; font-size:11px;")

        reset_btn = QPushButton("↺  Reset Learning")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #e5534b;
                border: 1px solid #fca5a5;
                border-radius: 7px;
                padding: 7px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background:#fef2f2; border-color:#e5534b; }
        """)
        reset_btn.clicked.connect(self._reset)

        bottom.addWidget(self._status_lbl)
        bottom.addStretch()
        bottom.addWidget(reset_btn)
        layout.addLayout(bottom)

        self._refresh()

    def _refresh(self):
        if self._engine is None:
            self._status_lbl.setText("Adaptive engine not running.")
            return

        summary = self._engine.get_stats_summary()

        # Clear existing rows
        while self._stats_layout.count():
            item = self._stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not summary:
            placeholder = QLabel("No gestures recorded yet.\nUse Wavly for a while to see stats here.")
            placeholder.setStyleSheet("color:#aaa; font-size:11px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stats_layout.addWidget(placeholder)
        else:
            for gesture, info in sorted(summary.items()):
                row = self._make_row(gesture, info)
                self._stats_layout.addWidget(row)

        self._stats_layout.addStretch()

        total_fires = sum(v["fires"] for v in summary.values())
        self._status_lbl.setText(f"{total_fires} gestures recorded this session")

    def _make_row(self, gesture: str, info: dict) -> QWidget:
        row = QFrame()
        row.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(14)

        # Gesture name
        name_lbl = QLabel(gesture.replace("_", " ").title())
        name_lbl.setFixedWidth(110)
        name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))

        # Fire count with health indicator
        fires = info['fires']
        fires_indicator = "●" if fires >= 10 else "○"
        fires_lbl = QLabel(f"{fires_indicator} {fires} fires")
        fires_lbl.setStyleSheet("color:#555; font-size:11px;")
        fires_lbl.setFixedWidth(75)

        # Misfire rate — colour coded with visual indicator
        mr = info["misfire_rate"]
        if mr < 10:
            mr_color = "#22c55e"
            mr_icon = "✓"
        elif mr < 25:
            mr_color = "#f59e0b"
            mr_icon = "⚠"
        else:
            mr_color = "#e5534b"
            mr_icon = "✗"
        
        mr_lbl = QLabel(f"{mr_icon} {mr:.1f}% misfire")
        mr_lbl.setStyleSheet(f"color:{mr_color}; font-weight:600; font-size:11px;")
        mr_lbl.setFixedWidth(100)

        # Mean confidence level
        conf = info['mean_conf']
        if conf >= 75:
            conf_color = "#22c55e"
        elif conf >= 60:
            conf_color = "#f59e0b"
        else:
            conf_color = "#94a3b8"
        
        conf_lbl = QLabel(f"{conf:.0f}% conf")
        conf_lbl.setStyleSheet(f"color:{conf_color}; font-size:11px;")
        conf_lbl.setFixedWidth(70)

        # Adapted values with icons
        hold      = info["hold_frames"]
        threshold = info["threshold"]
        adapted_parts = []
        
        if hold is not None:
            adapted_parts.append(f"⏱{hold}")
        if threshold is not None:
            adapted_parts.append(f"📊{threshold:.2f}")
        
        if adapted_parts:
            adapted_str = "  ".join(adapted_parts)
            adapted_lbl = QLabel(adapted_str)
            adapted_lbl.setStyleSheet("color:#3b82f6; font-size:10px; font-weight:500;")
            adapted_lbl.setFixedWidth(120)
        else:
            adapted_lbl = QLabel("default params")
            adapted_lbl.setStyleSheet("color:#9ca3af; font-size:10px;")
            adapted_lbl.setFixedWidth(120)

        hl.addWidget(name_lbl)
        hl.addWidget(fires_lbl)
        hl.addWidget(mr_lbl)
        hl.addWidget(conf_lbl)
        hl.addWidget(adapted_lbl, 1)

        return row

    def _toggle_enabled(self, checked: bool):
        if self._engine:
            self._engine.set_enabled(checked)

    def _reset(self):
        reply = QMessageBox.question(
            self,
            "Reset Learning",
            "This will erase all learned gesture data and restore default sensitivity.\n\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes and self._engine:
            self._engine.reset()
            self._refresh()