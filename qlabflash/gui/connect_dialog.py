"""Dialog: pick a QLab instance, discover its open workspaces, connect."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout,
)

from ..config import Config
from ..qlab import QLabClient
from .worker import run_async


class ConnectDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Connect to QLab")
        self.setMinimumWidth(440)

        self.client: Optional[QLabClient] = None
        self.workspace_id: Optional[str] = None
        self.workspace_name: str = ""
        self.mock = None  # holds the in-process MockQLab when in demo mode

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.host_edit = QLineEdit(self.config.qlab_host)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.config.qlab_port)
        self.passcode_edit = QLineEdit(self.config.passcode)
        self.passcode_edit.setEchoMode(QLineEdit.Password)
        self.passcode_edit.setPlaceholderText("only if the workspace has one")
        form.addRow("QLab host / IP:", self.host_edit)
        form.addRow("QLab port:", self.port_spin)
        form.addRow("Passcode:", self.passcode_edit)
        layout.addLayout(form)

        self.demo_check = QCheckBox(
            "Demo mode (run a simulated QLab on this Mac — no real QLab needed)")
        self.demo_check.toggled.connect(self._on_demo_toggled)
        layout.addWidget(self.demo_check)

        discover_row = QHBoxLayout()
        self.discover_btn = QPushButton("Discover Workspaces")
        self.discover_btn.clicked.connect(self._discover)
        discover_row.addWidget(self.discover_btn)
        discover_row.addStretch(1)
        layout.addLayout(discover_row)

        layout.addWidget(QLabel("Open workspaces:"))
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._connect())
        layout.addWidget(self.list_widget)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.connect_btn = self.buttons.addButton(
            "Connect", QDialogButtonBox.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.Cancel)
        self.connect_btn.clicked.connect(self._connect)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    # -- helpers ------------------------------------------------------------
    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_demo_toggled(self, checked: bool) -> None:
        self.host_edit.setEnabled(not checked)
        self.port_spin.setEnabled(not checked)
        if checked:
            self.host_edit.setText("127.0.0.1")

    def _ensure_client(self) -> QLabClient:
        """(Re)create the OSC client, starting the mock server in demo mode."""
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.mock is not None:
            self.mock.close()
            self.mock = None

        if self.demo_check.isChecked():
            from ..mock_qlab import MockQLab
            self.mock = MockQLab(host="127.0.0.1", port=0,
                                 mic_count=self.config.mic_count)
            host, port = "127.0.0.1", self.mock.port
        else:
            host, port = self.host_edit.text().strip(), self.port_spin.value()

        self.client = QLabClient(host=host, send_port=port, listen_port=0,
                                 reply_timeout=self.config.reply_timeout)
        return self.client

    # -- actions ------------------------------------------------------------
    def _discover(self) -> None:
        self._set_status("Searching for workspaces…")
        self.list_widget.clear()
        self.discover_btn.setEnabled(False)
        client = self._ensure_client()

        def work(progress):
            return client.workspaces()

        def done(workspaces: List[dict]):
            self.discover_btn.setEnabled(True)
            self._populate(workspaces)

        def error(msg: str):
            self.discover_btn.setEnabled(True)
            self._set_status(f"Could not reach QLab: {msg}")

        run_async(work, on_done=done, on_error=error)

    def _populate(self, workspaces: List[dict]) -> None:
        if not workspaces:
            self._set_status(
                "No workspaces found. Is QLab running, the workspace open, and "
                "is “OSC access” enabled in Workspace Settings → Network?")
            return
        for ws in workspaces:
            name = ws.get("displayName") or ws.get("uniqueID", "?")
            locked = " 🔒" if ws.get("hasPasscode") else ""
            item = QListWidgetItem(f"{name}{locked}")
            item.setData(Qt.UserRole, ws)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        self._set_status(f"Found {len(workspaces)} workspace(s). "
                         "Select one and click Connect.")

    def _connect(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            self._set_status("Pick a workspace first (or click Discover).")
            return
        ws = item.data(Qt.UserRole)
        workspace_id = ws.get("uniqueID")
        passcode = self.passcode_edit.text()
        self._set_status("Connecting…")
        self.connect_btn.setEnabled(False)
        client = self.client

        def work(progress):
            return client.connect_workspace(workspace_id, passcode)

        def done(status: str):
            self.connect_btn.setEnabled(True)
            if status in ("ok", "", None) or (isinstance(status, str)
                                              and status.startswith("ok")):
                self.workspace_id = workspace_id
                self.workspace_name = ws.get("displayName", workspace_id)
                self.config.qlab_host = self.host_edit.text().strip()
                self.config.qlab_port = self.port_spin.value()
                self.config.passcode = passcode
                self.accept()
            elif status == "badpass":
                self._set_status("Incorrect passcode — try again.")
            else:
                self._set_status(f"QLab refused the connection: {status}")

        def error(msg: str):
            self.connect_btn.setEnabled(True)
            self._set_status(f"Connection failed: {msg}")

        run_async(work, on_done=done, on_error=error)

    def reject(self) -> None:
        # Tear down sockets if the user cancels.
        if self.client is not None and self.workspace_id is None:
            self.client.close()
            self.client = None
        if self.mock is not None and self.workspace_id is None:
            self.mock.close()
            self.mock = None
        super().reject()
