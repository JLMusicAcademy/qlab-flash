"""Main application window."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QModelIndex, QObject, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..qlab import QLabClient
from ..session import WorkspaceSession
from .about import AboutDialog, ContactDialog, HelpDialog
from .diagnose_dialog import DiagnoseDialog
from .header import MicHeaderView
from .mixer_dialog import MixerDialog
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

        # Recounting unsaved changes walks the whole cue tree, so we coalesce
        # the many signals a single gesture fires (each click emits dataChanged
        # *and* micChanged; a bulk edit emits one per cell) into one refresh on
        # the next event-loop tick.
        self._dirty_timer = QTimer(self)
        self._dirty_timer.setSingleShot(True)
        self._dirty_timer.setInterval(0)
        self._dirty_timer.timeout.connect(self._do_refresh_dirty)

        self.setWindowTitle(f"QLab Flash — {workspace_name}")
        self.resize(1150, 720)
        self._build_ui()
        self._build_menus()
        self._wire_logging()
        self._load_grid(0)

    # -- menu bar -----------------------------------------------------------
    def _build_menus(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")

        about_act = QAction("About QLab Flash", self)
        about_act.setMenuRole(QAction.AboutRole)   # macOS moves this to the app menu
        about_act.triggered.connect(lambda: AboutDialog(self).exec())
        help_menu.addAction(about_act)

        help_act = QAction("QLab Flash Help", self)
        help_act.setShortcut(QKeySequence.HelpContents)
        help_act.triggered.connect(lambda: HelpDialog(self).exec())
        help_menu.addAction(help_act)

        contact_act = QAction("Contact", self)
        contact_act.triggered.connect(lambda: ContactDialog(self).exec())
        help_menu.addAction(contact_act)

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
        self.collapse_btn = QPushButton("Collapse to cues")
        self.collapse_btn.setToolTip(
            "Collapse so each mic cue shows as one row with its 32 mics.")
        self.collapse_btn.clicked.connect(self._collapse_to_cues)
        top.addWidget(self.collapse_btn)

        self.names_btn = QPushButton("Mic names…")
        self.names_btn.setToolTip(
            "Name your mics (e.g. actor/role names). A name shows in the column "
            "header, renames that mic's cue everywhere it appears, and sets the "
            "channel name on the X32 — all applied when you Submit.")
        self.names_btn.clicked.connect(self._edit_names)
        top.addWidget(self.names_btn)

        self.mixer_btn = QPushButton("Mixer…")
        self.mixer_btn.setToolTip(
            "Set the X32's IP address so mic names also update the console's "
            "scribble strips.")
        self.mixer_btn.clicked.connect(self._edit_mixer)
        top.addWidget(self.mixer_btn)

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
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setToolTip("Undo the last change (⌘Z). Up to 30 steps.")
        self.undo_btn.clicked.connect(self._undo)
        bulk.addWidget(self.undo_btn)
        bulk.addStretch(1)
        hint = QLabel("Drag to select a block · double-click a name to rename · "
                      "Space toggles · 1 unmutes · 0 mutes · ⌘Z undo")
        hint.setStyleSheet("color: #777;")
        bulk.addWidget(hint)
        root.addLayout(bulk)

        QShortcut(QKeySequence.Undo, self, self._undo)

        # The worksheet tree, with a header that can show mic names vertically.
        self.tree = CueTreeView()
        self.header = MicHeaderView(self.config.label_for, self.tree)
        self.tree.setHeader(self.header)
        self.header.sectionDoubleClicked.connect(self._rename_channel)
        self.tree.selectionChangedCount.connect(self._on_selection_count)
        self.tree.hoverCell.connect(self._on_hover_cell)
        root.addWidget(self.tree, 1)

        # Bottom bar: dirty count + submit.
        bottom = QHBoxLayout()
        self.dirty_label = QLabel("No changes")
        bottom.addWidget(self.dirty_label)
        bottom.addStretch(1)
        # Live readout of the mic under the cursor, so you always know which
        # column you're in on a wide grid.
        self.readout_label = QLabel("")
        self.readout_label.setStyleSheet("color: #1a3d6d; font-weight: bold;")
        bottom.addWidget(self.readout_label)
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
            "Write every mic in every cue, not just the ones you changed "
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
    def _sync_cuelist_combo(self) -> None:
        """Refresh the cue-list dropdown from the freshly-read cue lists."""
        cur = self.cuelist_combo.currentIndex()
        self.cuelist_combo.blockSignals(True)
        self.cuelist_combo.clear()
        for cl in self.session.cue_lists:
            self.cuelist_combo.addItem(cl.name or cl.uid)
        if self.cuelist_combo.count():
            self.cuelist_combo.setCurrentIndex(
                max(0, min(cur, self.cuelist_combo.count() - 1)))
        self.cuelist_combo.blockSignals(False)

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
            self._sync_cuelist_combo()
            # Detach the previous model first so nothing references stale rows.
            old = self.tree_model
            self.tree.setModel(None)
            self.tree_model = CueTreeModel(model, self.config)
            self.tree_model.dataChanged.connect(lambda *_: self._refresh_dirty())
            self.tree_model.micChanged.connect(self._on_mic_changed)
            self.tree.setModel(self.tree_model)
            if old is not None:
                old.deleteLater()
            self._format_tree()
            self._collapse_to_cues()
            self._set_busy(False)
            self._refresh_dirty()
            mic_cues = len(model.anchors())
            total = sum(1 for _ in model.iter_rows())
            if mic_cues == 0 and model.placeholder_count:
                msg = (f"Found {model.placeholder_count} On/Off cue(s), but their "
                       f"Channel is a {{channel}} placeholder. In QLab, set each "
                       f"cue's Channel to a number (01–32) so it maps to a mic.")
                self.statusBar().showMessage(msg)
                QMessageBox.information(self, "Cues need a channel number", msg)
            else:
                self.statusBar().showMessage(
                    f"Loaded {mic_cues} cue(s) with mics, {total} cue(s) total.")

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
    def _collapse_to_cues(self) -> None:
        """Expand structure down to mic-cue rows, collapsing each one's mics."""
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

    # -- mic names (column headers + QLab cue names) ------------------------
    def _apply_channel_name(self, chan: int, name: str) -> None:
        """Set the column label and (via the model) the channel's cue names."""
        if self.tree_model is not None:
            self.tree_model.rename_channel(chan, name)
        else:
            self.config.set_label(chan, name)

    def _rename_channel(self, logical_index: int) -> None:
        if logical_index < 1:
            return
        chan = logical_index
        current = self.config.label_for(chan)
        mixer = "the X32 channel name" if self.config.x32_host else \
                "the X32 channel name (set the mixer IP in Mixer…)"
        name, ok = QInputDialog.getText(
            self, f"Name mic {chan}",
            f"Name for mic {chan} (e.g. an actor/role).\n\nOn Submit this will:\n"
            f"  • label this column,\n"
            f"  • rename mic {chan}'s cue everywhere it appears in QLab,\n"
            f"  • set {mixer}.",
            text=current)
        if not ok or name.strip() == current:
            return
        self._apply_channel_name(chan, name)
        self._save_config()
        self._after_name_change()

    def _edit_mixer(self) -> None:
        dialog = MixerDialog(self.config, self)
        if dialog.exec():
            dialog.apply_to_config()
            self._save_config()
            self._refresh_dirty()

    def _edit_names(self) -> None:
        dialog = NamesDialog(self.config, self)
        if not dialog.exec():
            return
        for chan, name in dialog.values().items():
            if name.strip() != self.config.label_for(chan):
                self._apply_channel_name(chan, name)
        self._save_config()
        self._after_name_change()

    def _after_name_change(self) -> None:
        self._apply_header_labels()
        if self.tree_model is not None:
            self.tree.viewport().update()
        self._refresh_dirty()

    def _undo(self) -> None:
        if self.tree_model is None or not self.tree_model.undo():
            self.statusBar().showMessage("Nothing to undo.")
            return
        self._save_config()          # labels may have changed
        self._after_name_change()
        self.statusBar().showMessage("Undid last change.")

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
        # Repaint so aliased cells (an anchor cue and the mic cue beneath) match.
        self.tree.viewport().update()
        self._refresh_dirty()

    def _on_selection_count(self, count: int) -> None:
        if count:
            self.statusBar().showMessage(f"{count} mic cell(s) selected.")

    def _on_hover_cell(self, channel: int) -> None:
        if channel is None or channel < 1:
            self.readout_label.setText("")
            return
        name = self.config.label_for(channel)
        self.readout_label.setText(f"Mic {channel} — {name}" if name
                                   else f"Mic {channel}")

    # -- submit -------------------------------------------------------------
    def _submit(self, only_dirty: bool) -> None:
        if self.tree_model is None:
            return
        model = self.session.model
        mic_writes = model.dirty_writes() if only_dirty else model.all_writes()
        name_writes = model.name_writes()
        scribble = model.scribble_writes(only_dirty=only_dirty)
        if not mic_writes and not name_writes and not scribble:
            QMessageBox.information(self, "Nothing to send",
                                    "There are no changes to submit.")
            return
        parts = []
        if mic_writes:
            parts.append(f"{len(mic_writes)} mic setting(s)")
        if name_writes:
            parts.append(f"{len(name_writes)} cue name(s)")
        if scribble:
            where = "X32" if self.config.x32_host else "X32 (no mixer IP set — will skip)"
            parts.append(f"{len(scribble)} mixer name(s) → {where}")
        if QMessageBox.question(
                self, "Submit",
                "Send " + " and ".join(parts) + " now?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.statusBar().showMessage("Sending to QLab…")

        def work(progress):
            return self.session.submit(only_dirty=only_dirty)

        def done(result):
            mics, names, scribble = result
            self._set_busy(False)
            self._refresh_dirty()
            if self.tree_model:
                self.tree.viewport().update()
            msg = (f"Sent {mics} mic update(s) and {names} cue name(s) to QLab"
                   f", and {scribble} mixer name(s) to the X32.")
            if scribble == 0 and names and not self.config.x32_host:
                msg += "  (Set the mixer IP in Mixer… to update scribble strips.)"
            self.statusBar().showMessage(msg)

        run_async(work, on_done=done, on_error=self._on_error)

    # -- state helpers ------------------------------------------------------
    def _dirty_total(self) -> int:
        if not self.tree_model:
            return 0
        return self.tree_model.mic_dirty_count() + self.tree_model.name_dirty_count()

    def _refresh_dirty(self) -> None:
        # Coalesce: many edit signals in one gesture collapse to a single
        # recount on the next tick instead of walking the tree for each.
        self._dirty_timer.start()

    def _do_refresh_dirty(self) -> None:
        if not self.tree_model:
            self.dirty_label.setText("No changes")
            self.submit_btn.setEnabled(False)
            return
        mics = self.tree_model.mic_dirty_count()
        names = self.tree_model.name_dirty_count()
        scribble = self.tree_model.scribble_dirty_count()
        if not mics and not names and not scribble:
            self.dirty_label.setText("No changes")
        else:
            bits = []
            if mics:
                bits.append(f"{mics} mic")
            if names:
                bits.append(f"{names} name")
            if scribble:
                bits.append(f"{scribble} mixer name")
            self.dirty_label.setText(" + ".join(bits) + " change(s) unsaved")
        self.submit_btn.setEnabled(mics > 0 or names > 0 or scribble > 0)

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
