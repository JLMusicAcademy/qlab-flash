"""Main application window."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..qlab import QLabClient
from ..session import WorkspaceSession
from .table_model import MicTableModel
from .table_view import MicTableView
from .worker import run_async

MIC_COL_WIDTH = 30


class _LogBridge(QObject):
    """Marshals OSC log lines from the network thread to the UI thread."""
    line = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, client: QLabClient, workspace_id: str,
                 workspace_name: str, config: Config, mock=None):
        super().__init__()
        self.client = client
        self.config = config
        self.mock = mock  # keep the demo server alive for the window's lifetime
        self.session = WorkspaceSession(client, workspace_id, config)
        self.table_model: Optional[MicTableModel] = None

        self.setWindowTitle(f"QLab Flash — {workspace_name}")
        self.resize(1100, 700)
        self._build_ui()
        self._wire_logging()
        self._load_cue_lists()

    # -- UI construction ----------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Top control bar.
        top = QHBoxLayout()
        top.addWidget(QLabel("Cue list:"))
        self.cuelist_combo = QComboBox()
        self.cuelist_combo.currentIndexChanged.connect(self._on_cuelist_changed)
        top.addWidget(self.cuelist_combo, 1)

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._reload)
        top.addWidget(self.reload_btn)
        root.addLayout(top)

        # Bulk-edit bar.
        bulk = QHBoxLayout()
        for label, handler in (
            ("Unmute selected", lambda: self._bulk(True)),
            ("Mute selected", lambda: self._bulk(False)),
            ("Toggle selected", self._bulk_toggle),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            bulk.addWidget(btn)
        bulk.addSpacing(20)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.clicked.connect(self._select_all)
        bulk.addWidget(self.select_all_btn)
        bulk.addStretch(1)
        hint = QLabel("Drag to select a block · Space toggles · 1 unmutes · 0 mutes")
        hint.setStyleSheet("color: #777;")
        bulk.addWidget(hint)
        root.addLayout(bulk)

        # The grid.
        self.table = MicTableView()
        self.table.selectionChangedCount.connect(self._on_selection_count)
        root.addWidget(self.table, 1)

        # Bottom bar: dirty count + submit.
        bottom = QHBoxLayout()
        self.dirty_label = QLabel("No changes")
        bottom.addWidget(self.dirty_label)
        bottom.addStretch(1)
        self.log_toggle = QPushButton("Show OSC log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        bottom.addWidget(self.log_toggle)
        self.submit_btn = QPushButton("Submit changed cues to QLab")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(lambda: self._submit(only_dirty=True))
        bottom.addWidget(self.submit_btn)
        self.submit_all_btn = QPushButton("Submit ALL")
        self.submit_all_btn.setToolTip(
            "Write every mic in every cue, not just the ones you changed.")
        self.submit_all_btn.clicked.connect(lambda: self._submit(only_dirty=False))
        bottom.addWidget(self.submit_all_btn)
        root.addLayout(bottom)

        # Collapsible OSC log.
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setFixedHeight(140)
        self.log_view.hide()
        root.addWidget(self.log_view)

        self.statusBar().showMessage("Ready.")

    def _wire_logging(self) -> None:
        self._log_bridge = _LogBridge()
        self._log_bridge.line.connect(self.log_view.appendPlainText)

        def logger(direction, address, detail):
            arrow = "→" if direction == "send" else "←"
            self._log_bridge.line.emit(f"{arrow} {address}  {detail}")

        self.client.set_logger(logger)

    # -- loading ------------------------------------------------------------
    def _load_cue_lists(self) -> None:
        self.statusBar().showMessage("Reading cue lists…")
        self._set_busy(True)

        def work(progress):
            return self.session.fetch_cue_lists()

        def done(cue_lists):
            self.cuelist_combo.blockSignals(True)
            self.cuelist_combo.clear()
            for cl in cue_lists:
                self.cuelist_combo.addItem(cl.name or cl.uid)
            self.cuelist_combo.blockSignals(False)
            if cue_lists:
                self._load_grid(0)
            else:
                self._set_busy(False)
                self.statusBar().showMessage("No cue lists in this workspace.")

        run_async(work, on_done=done, on_error=self._on_error)

    def _on_cuelist_changed(self, index: int) -> None:
        if index >= 0:
            self._load_grid(index)

    def _reload(self) -> None:
        idx = max(0, self.cuelist_combo.currentIndex())
        self._load_grid(idx)

    def _load_grid(self, index: int) -> None:
        if self._has_unsaved() and not self._confirm_discard():
            return
        self.statusBar().showMessage("Reading mic states from QLab…")
        self._set_busy(True)

        def work(progress):
            return self.session.load_grid(index, progress=progress)

        def done(model):
            self.table_model = MicTableModel(model)
            self.table_model.dataChanged.connect(lambda *_: self._refresh_dirty())
            self.table.setModel(self.table_model)
            self._format_table()
            self._set_busy(False)
            self._refresh_dirty()
            self.statusBar().showMessage(
                f"Loaded {len(model.rows)} cue(s).")

        run_async(work, on_done=done, on_error=self._on_error,
                  on_progress=lambda msg: self.statusBar().showMessage(msg))

    def _format_table(self) -> None:
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 220)
        for col in range(1, self.table_model.columnCount()):
            self.table.setColumnWidth(col, MIC_COL_WIDTH)
        self.table.verticalHeader().setDefaultSectionSize(24)

    # -- bulk edit ----------------------------------------------------------
    def _bulk(self, unmuted: bool) -> None:
        if self.table_model is None:
            return
        n = self.table.set_selected(unmuted)
        self.statusBar().showMessage(
            f"{'Unmuted' if unmuted else 'Muted'} {n} mic(s).")
        self._refresh_dirty()

    def _bulk_toggle(self) -> None:
        if self.table_model is None:
            return
        n = self.table.toggle_selected()
        self.statusBar().showMessage(f"Toggled {n} mic(s).")
        self._refresh_dirty()

    def _select_all(self) -> None:
        self.table.selectAll()

    def _on_selection_count(self, count: int) -> None:
        if count:
            self.statusBar().showMessage(f"{count} mic cell(s) selected.")

    # -- submit -------------------------------------------------------------
    def _submit(self, only_dirty: bool) -> None:
        if self.table_model is None:
            return
        writes = (self.session.model.dirty_writes() if only_dirty
                  else self.session.model.all_writes())
        if not writes:
            QMessageBox.information(self, "Nothing to send",
                                    "There are no changes to submit.")
            return
        verb = "changed" if only_dirty else "ALL"
        if QMessageBox.question(
                self, "Submit to QLab",
                f"Send {len(writes)} {verb} mic setting(s) to QLab now?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.statusBar().showMessage("Sending to QLab…")

        def work(progress):
            return self.session.submit(only_dirty=only_dirty)

        def done(count):
            self._set_busy(False)
            self._refresh_dirty()
            if self.table_model:
                self.table_model.layoutChanged.emit()
            self.statusBar().showMessage(f"Sent {count} cue update(s) to QLab.")

        run_async(work, on_done=done, on_error=self._on_error)

    # -- state helpers ------------------------------------------------------
    def _refresh_dirty(self) -> None:
        n = self.table_model.dirty_count() if self.table_model else 0
        self.dirty_label.setText("No changes" if n == 0
                                 else f"{n} unsaved change(s)")
        self.submit_btn.setEnabled(n > 0)

    def _has_unsaved(self) -> bool:
        return bool(self.table_model and self.table_model.dirty_count())

    def _confirm_discard(self) -> bool:
        return QMessageBox.question(
            self, "Discard changes?",
            "You have unsaved mic changes. Reload and lose them?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

    def _set_busy(self, busy: bool) -> None:
        for w in (self.reload_btn, self.submit_btn, self.submit_all_btn,
                  self.cuelist_combo, self.table):
            w.setEnabled(not busy)
        if not busy:
            self._refresh_dirty()

    def _toggle_log(self, checked: bool) -> None:
        self.log_view.setVisible(checked)
        self.log_toggle.setText("Hide OSC log" if checked else "Show OSC log")

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.statusBar().showMessage("Error.")
        QMessageBox.critical(self, "QLab error", message)

    # -- shutdown -----------------------------------------------------------
    def closeEvent(self, event):
        if self._has_unsaved() and not self._confirm_discard():
            event.ignore()
            return
        try:
            self.client.close()
        finally:
            if self.mock is not None:
                self.mock.close()
        super().closeEvent(event)
