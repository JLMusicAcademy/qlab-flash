"""Dialog to set the X32 mixer address (for scribble-strip channel names)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox,
    QVBoxLayout,
)

from ..config import Config


class MixerDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("X32 mixer")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        info = QLabel(
            "Enter your X32's IP address so renaming a mic can also set the "
            "channel name on the console (scribble strip). Leave the IP blank "
            "to skip mixer updates. The X32 listens on port 10023.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.host_edit = QLineEdit(config.x32_host)
        self.host_edit.setPlaceholderText("e.g. 192.168.1.50")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(config.x32_port)
        form.addRow("X32 IP address:", self.host_edit)
        form.addRow("X32 OSC port:", self.port_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to_config(self) -> None:
        self.config.x32_host = self.host_edit.text().strip()
        self.config.x32_port = self.port_spin.value()
