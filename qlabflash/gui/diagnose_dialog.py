"""Diagnostic: dump a cue's QLab properties to discover how it stores values.

Used to figure out how X32 "network audio" cues keep their on/off value, since
QLab's property names for patch-based network cues aren't documented.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from ..model import Cue
from .worker import run_async

# A broad set of candidate property names; the ones that exist will reveal how
# the cue stores its channel/value data.
PROBE_KEYS = [
    "type", "name", "number", "listName",
    "messageType", "customString", "parameterValues",
    "oscMessageType", "networkMessageType", "customMessageType",
    "collectionType", "patchNumber", "patch", "patchDisplayName",
    "value", "doubleValue", "stringValue", "parameterValue",
    "channelNumbers", "channel", "oscString", "message", "rawMessage",
    "deviceMessageType", "mixerMessageType", "qlabMessageType",
]


def _flatten(cues: List[Cue], depth=0, out=None):
    if out is None:
        out = []
    for c in cues:
        label = f"{'  ' * depth}{c.number or '–'}  {c.name}  [{c.type}]"
        out.append((label, c.uid))
        _flatten(c.children, depth + 1, out)
    return out


class DiagnoseDialog(QDialog):
    def __init__(self, client, workspace_id: str, cue_lists: List[Cue], parent=None):
        super().__init__(parent)
        self.client = client
        self.workspace_id = workspace_id
        self.setWindowTitle("Diagnose cue properties")
        self.resize(640, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Pick one of your mic mute/unmute cues and click Probe. Then click "
            "“Copy results” and send them back so I can wire the app to your "
            "X32 cues."))

        row = QHBoxLayout()
        self.combo = QComboBox()
        for label, uid in _flatten(cue_lists):
            self.combo.addItem(label, uid)
        row.addWidget(self.combo, 1)
        self.probe_btn = QPushButton("Probe")
        self.probe_btn.clicked.connect(self._probe)
        row.addWidget(self.probe_btn)
        layout.addLayout(row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

        bottom = QHBoxLayout()
        self.copy_btn = QPushButton("Copy results")
        self.copy_btn.clicked.connect(self._copy)
        bottom.addWidget(self.copy_btn)
        bottom.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _probe(self):
        uid = self.combo.currentData()
        if not uid:
            return
        self.output.setPlainText("Probing…")
        self.probe_btn.setEnabled(False)

        def work(progress):
            return self.client.probe_cue(self.workspace_id, uid, PROBE_KEYS)

        def done(results):
            self.probe_btn.setEnabled(True)
            lines = [f"Cue: {self.combo.currentText().strip()}", ""]
            for key in PROBE_KEYS:
                status, data = results.get(key, ("(none)", None))
                lines.append(f"{key}: status={status}  data={data!r}")
            self.output.setPlainText("\n".join(lines))

        def error(msg):
            self.probe_btn.setEnabled(True)
            self.output.setPlainText(f"Error: {msg}")

        run_async(work, on_done=done, on_error=error)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.output.toPlainText())
