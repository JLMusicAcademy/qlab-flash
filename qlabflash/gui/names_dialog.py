"""Dialog for editing all mic names at once (e.g. assign actor names)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..config import Config


class NamesDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Mic names")
        self.resize(300, 560)
        self._edits = {}

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        for chan in range(1, config.mic_count + 1):
            edit = QLineEdit(config.label_for(chan))
            edit.setPlaceholderText(f"Mic {chan}")
            self._edits[chan] = edit
            form.addRow(f"{chan}:", edit)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        clear_btn = QPushButton("Clear all names")
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _clear(self) -> None:
        for edit in self._edits.values():
            edit.clear()

    def apply_to_config(self) -> None:
        """Write the edited names back into the config object."""
        for chan, edit in self._edits.items():
            self.config.set_label(chan, edit.text())
