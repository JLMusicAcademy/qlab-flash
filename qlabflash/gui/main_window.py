"""Main application window."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QModelIndex, QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..qlab import QLabClient
from ..session import WorkspaceSession
from .diagnose_dialog import DiagnoseDialog
from .header import MicHeaderView
from .names_dialog import NamesDialog
from .tree_model import CueTreeModel
from .tree_view import CueTreeView
from .worker import run_async

MIC_COL_WIDTH = 30
NAME_COL_WIDTH = 300
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.qlab-flash.json")


class _LogBridge(QObject):
    """Marshals OSC log lines from the network thread to the UI thread."""
    line = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, client: QLabClient, workspace_id: str,
                 workspace_name: str, config: Config, mock=None,
                 config_path: str = DEFAULT_CONFIG_PATH):
        super().__init__()
        self.client = client
        self.config = config
        self.config_path = config_path
        self.mock = mock  # keep the demo server alive for the window's lifetime
        self.session = WorkspaceSession(client, workspace_id, config)
        self.tree_model: Optional[CueTreeModel] = None

        self.setWindowTitle(f"QLab Flash — {workspace_name}")
        self.resize(1150, 720)
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

        self.expand_btn = QPushButton("Expand all")
        self.expand_btn.clicked.connect(lambda: self.tree.expandAll())
        top.addWidget(self.expand_btn)
        self.collapse_btn = QPushButton("Collapse to looks")
        self.collapse_btn.setToolTip(
            "Collapse so each mic 'look' shows as one row with its 32 mics.")
        self.collapse_btn.clicked.connect(self._collapse_to_looks)
        top.addWidget(self.collapse_btn)

        self.names_btn = QPushButton("Mic names…")
        self.names_btn.setToolTip(
            "Give mics friendly names (e.g. actor names) shown in the column "
            "headers. Tip: you can also double-click a mic's header to rename "
            "just that one.")
        self.names_btn.clicked.connect(self._edit_names)
        top.addWidget(self.names_btn)

        self.diagnose_btn = QPushButton("Diagnose…")
        self.diagnose_btn.setToolTip(
            "Inspect a cue's QLab properties (for troubleshooting).")
        self.diagnose_btn.clicked.connect(self._diagnose)
        top.addWidget(self.diagnose_btn)

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
        self.select_all_btn.clicked.connect(lambda: self.tree.selectAll())
        bulk.addWidget(self.select_all_btn)
        bulk.addStretch(1)
        hint = QLabel("Drag to select a block · double-click a name to rename · "
                      "Space toggles · 1 unmutes · 0 mutes")
        hint.setStyleSheet("color: #777;")
        bulk.addWidget(hint)
        root.addLayout(bulk)

        # The worksheet tree, with a header that can show mic names vertically.
        self.tree = CueTreeView()
        self.header = MicHeaderView(self.config.label_for, self.tree)
        self.tree.setHeader(self.header)
        self.header.sectionDoubleClicked.connect(self._rename_channel)
        self.tree.selectionChangedCount.connect(self._on_selection_count)
        root.addWidget(self.tree, 1)

        # Bottom bar: dirty count + submit.
        bottom = QHBoxLayout()
        self.dirty_label = QLabel("No changes")
        bottom.addWidget(self.dirty_label)
        bottom.addStretch(1)
        self.log_toggle = QPushButton("Show OSC log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        bottom.addWidget(self.log_toggle)
        self.submit_btn = QPushButton("Submit changes to QLab")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(lambda: self._submit(only_dirty=True))
        bottom.addWidget(self.submit_btn)
        self.submit_all_btn = QPushButton("Submit ALL mics")
        self.submit_all_btn.setToolTip(
            "Write every mic in every look, not just the ones you changed "
            "(plus any name edits).")
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
        self._load_grid(max(0, self.cuelist_combo.currentIndex()))

    def _diagnose(self) -> None:
        if not self.session.cue_lists:
            QMessageBox.information(self, "Diagnose",
                                    "Connect and load a workspace first.")
            return
        DiagnoseDialog(self.client, self.session.workspace_id,
                       self.session.cue_lists, self).exec()

    def _load_grid(self, index: int) -> None:
        if self._has_unsaved() and not self._confirm_discard():
            return
        self.statusBar().showMessage("Reading mic states from QLab…")
        self._set_busy(True)

        def work(progress):
            return self.session.load_grid(index, progress=progress)

        def done(model):
            self.tree_model = CueTreeModel(model, self.config)
            self.tree_model.dataChanged.connect(lambda *_: self._refresh_dirty())
            self.tree_model.micChanged.connect(self._on_mic_changed)
            self.tree.setModel(self.tree_model)
            self._format_tree()
            self._collapse_to_looks()
            self._set_busy(False)
            self._refresh_dirty()
            self.statusBar().showMessage(
                f"Loaded {len(model.anchors())} mic look(s) "
                f"across {sum(1 for _ in model.iter_rows())} cue(s).")

        run_async(work, on_done=done, on_error=self._on_error,
                  on_progress=lambda msg: self.statusBar().showMessage(msg))

    def _format_tree(self) -> None:
        self.header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.setColumnWidth(0, NAME_COL_WIDTH)
        for col in range(1, self.tree_model.columnCount()):
            self.tree.setColumnWidth(col, MIC_COL_WIDTH)
        self._apply_header_labels()

    def _apply_header_labels(self) -> None:
        """Grow/shrink the header for names and repaint it."""
        self.header.set_tall(self.config.has_labels())
        if self.tree_model is not None:
            self.tree_model.headerDataChanged.emit(
                Qt.Horizontal, 1, self.tree_model.columnCount() - 1)

    # -- expansion ----------------------------------------------------------
    def _collapse_to_looks(self) -> None:
        """Expand structure down to look rows, but collapse each look's mics."""
        if self.tree_model is None:
            return

        def walk(parent_index: QModelIndex):
            rows = self.tree_model.rowCount(parent_index)
            for r in range(rows):
                idx = self.tree_model.index(r, 0, parent_index)
                node = idx.internalPointer()
                if node.is_anchor:
                    self.tree.setExpanded(idx, False)
                else:
                    self.tree.setExpanded(idx, True)
                    walk(idx)

        walk(QModelIndex())

    # -- mic names (column headers) -----------------------------------------
    def _rename_channel(self, logical_index: int) -> None:
        if logical_index < 1:
            return
        chan = logical_index
        current = self.config.label_for(chan)
        name, ok = QInputDialog.getText(
            self, f"Name mic {chan}",
            f"Name for mic {chan} (blank to clear):", text=current)
        if not ok:
            return
        self.config.set_label(chan, name)
        self._save_config()
        self._apply_header_labels()

    def _edit_names(self) -> None:
        dialog = NamesDialog(self.config, self)
        if dialog.exec():
            dialog.apply_to_config()
            self._save_config()
            self._apply_header_labels()

    def _save_config(self) -> None:
        try:
            self.config.save(self.config_path)
        except OSError:
            pass

    # -- bulk edit ----------------------------------------------------------
    def _bulk(self, unmuted: bool) -> None:
        if self.tree_model is None:
            return
        n = self.tree.set_selected(unmuted)
        self.statusBar().showMessage(
            f"{'Unmuted' if unmuted else 'Muted'} {n} mic(s).")
        self._refresh_dirty()

    def _bulk_toggle(self) -> None:
        if self.tree_model is None:
            return
        n = self.tree.toggle_selected()
        self.statusBar().showMessage(f"Toggled {n} mic(s).")
        self._refresh_dirty()

    def _on_mic_changed(self) -> None:
        # Repaint so aliased cells (a look and the mic cue beneath it) match.
        self.tree.viewport().update()
        self._refresh_dirty()

    def _on_selection_count(self, count: int) -> None:
        if count:
            self.statusBar().showMessage(f"{count} mic cell(s) selected.")

    # -- submit -------------------------------------------------------------
    def _submit(self, only_dirty: bool) -> None:
        if self.tree_model is None:
            return
        model = self.session.model
        mic_writes = model.dirty_writes() if only_dirty else model.all_writes()
        name_writes = model.name_writes()
        if not mic_writes and not name_writes:
            QMessageBox.information(self, "Nothing to send",
                                    "There are no changes to submit.")
            return
        parts = []
        if mic_writes:
            parts.append(f"{len(mic_writes)} mic setting(s)")
        if name_writes:
            parts.append(f"{len(name_writes)} cue name(s)")
        if QMessageBox.question(
                self, "Submit to QLab",
                "Send " + " and ".join(parts) + " to QLab now?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.statusBar().showMessage("Sending to QLab…")

        def work(progress):
            return self.session.submit(only_dirty=only_dirty)

        def done(result):
            mics, names = result
            self._set_busy(False)
            self._refresh_dirty()
            if self.tree_model:
                self.tree.viewport().update()
            self.statusBar().showMessage(
                f"Sent {mics} mic update(s) and {names} name change(s) to QLab.")

        run_async(work, on_done=done, on_error=self._on_error)

    # -- state helpers ------------------------------------------------------
    def _dirty_total(self) -> int:
        if not self.tree_model:
            return 0
        return self.tree_model.mic_dirty_count() + self.tree_model.name_dirty_count()

    def _refresh_dirty(self) -> None:
        if not self.tree_model:
            self.dirty_label.setText("No changes")
            self.submit_btn.setEnabled(False)
            return
        mics = self.tree_model.mic_dirty_count()
        names = self.tree_model.name_dirty_count()
        if not mics and not names:
            self.dirty_label.setText("No changes")
        else:
            bits = []
            if mics:
                bits.append(f"{mics} mic")
            if names:
                bits.append(f"{names} name")
            self.dirty_label.setText(" + ".join(bits) + " change(s) unsaved")
        self.submit_btn.setEnabled(mics > 0 or names > 0)

    def _has_unsaved(self) -> bool:
        return self._dirty_total() > 0

    def _confirm_discard(self) -> bool:
        return QMessageBox.question(
            self, "Discard changes?",
            "You have unsaved changes. Reload and lose them?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

    def _set_busy(self, busy: bool) -> None:
        for w in (self.reload_btn, self.submit_btn, self.submit_all_btn,
                  self.cuelist_combo, self.tree):
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
