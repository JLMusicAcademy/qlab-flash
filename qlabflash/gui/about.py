"""About, Help, and Contact dialogs (and the menu bar that opens them)."""

from __future__ import annotations

import os
import urllib.parse

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout,
)

from .. import __release_date__, __version__

# --- Details --------------------------------------------------------------
DEVELOPER = "Ji-Eun Lee Music Academy, LLC"
CONTACT_EMAIL = "doug@fishersmusic.com"


def _icon_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base, "assets", "icon.png")


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About QLab Flash")
        self.setMinimumWidth(440)
        layout = QHBoxLayout(self)

        icon = QLabel()
        pm = QPixmap(_icon_path())
        if not pm.isNull():
            icon.setPixmap(pm.scaled(96, 96, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))
        icon.setAlignment(Qt.AlignTop)
        layout.addWidget(icon)

        text = QLabel(
            f"<h2 style='margin-bottom:2px;'>QLab Flash</h2>"
            f"<p style='color:#555; margin-top:0;'>Bulk mic mute/unmute editor "
            f"for QLab&nbsp;5 + Behringer&nbsp;X32</p>"
            f"<p><b>Version:</b> {__version__}<br>"
            f"<b>Released:</b> {__release_date__}</p>"
            f"<p>{DEVELOPER}<br>"
            f"<span style='color:#777;'>© 2026 {DEVELOPER}. All rights "
            f"reserved.</span></p>")
        text.setTextFormat(Qt.RichText)
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignTop)
        layout.addWidget(text, 1)


class ContactDialog(QDialog):
    """A small contact form that composes an email in the user's mail app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contact")
        self.resize(480, 440)
        layout = QVBoxLayout(self)

        intro = QLabel("Send us a message. This opens your email app with the "
                       f"message addressed to {CONTACT_EMAIL}, ready to send.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("so we can reply")
        self.subject_edit = QLineEdit("QLab Flash — Support")
        form.addRow("Your name:", self.name_edit)
        form.addRow("Your email:", self.email_edit)
        form.addRow("Subject:", self.subject_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Message:"))
        self.message_edit = QPlainTextEdit()
        layout.addWidget(self.message_edit, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close_btn = QPushButton("Cancel")
        close_btn.clicked.connect(self.reject)
        send_btn = QPushButton("Compose Email")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._compose)
        row.addWidget(close_btn)
        row.addWidget(send_btn)
        layout.addLayout(row)

    def _compose(self):
        lines = []
        who = " ".join(p for p in (self.name_edit.text().strip(),
                                   f"<{self.email_edit.text().strip()}>"
                                   if self.email_edit.text().strip() else "")
                       if p)
        if who:
            lines.append(f"From: {who}")
            lines.append("")
        lines.append(self.message_edit.toPlainText())
        query = urllib.parse.urlencode(
            {"subject": self.subject_edit.text(), "body": "\n".join(lines)},
            quote_via=urllib.parse.quote)
        QDesktopServices.openUrl(QUrl(f"mailto:{CONTACT_EMAIL}?{query}"))
        self.accept()


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QLab Flash Help")
        self.resize(760, 640)
        layout = QVBoxLayout(self)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(HELP_HTML)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


HELP_HTML = """
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; }
  h1 { font-size: 20px; }
  h2 { font-size: 15px; margin-top: 18px; color: #1a3d6d; }
  p, li { font-size: 13px; line-height: 1.45; }
  code, kbd { background:#eee; padding:1px 4px; border-radius:3px;
              font-family: Menlo, monospace; font-size: 12px; }
  .tip { background:#eef6ff; border-left:3px solid #2c6bbf; padding:6px 10px; }
</style>

<h1>QLab Flash — Help</h1>
<p>QLab Flash lets you set X32 mic mute/unmute states across an entire QLab show
from one spreadsheet, then push every change to QLab (and the mixer) at once.</p>
<p><b>A checked box = mic <u>unmuted</u> (channel ON). An unchecked box = mic
<u>muted</u> (channel OFF).</b></p>

<h2>1. Connecting</h2>
<ul>
  <li>In QLab: <b>Workspace Settings → Network → OSC Access</b> — enable access
      with permission to view/control cues (enter a passcode if your workspace
      uses one).</li>
  <li>Open QLab Flash, pick your workspace, enter the passcode if prompted, and
      click <b>Connect</b>. (Tick <b>Demo mode</b> to explore without QLab.)</li>
</ul>

<h2>2. The grid</h2>
<ul>
  <li><b>Rows</b> = your cues (the full QLab hierarchy on the left, expandable).</li>
  <li><b>Columns 1–32</b> = mics. A checkbox appears on any cue that controls
      that channel; cues without mics are blank.</li>
  <li>Green tint = a mic that's currently unmuted; amber tint = an edit you
      haven't submitted yet.</li>
</ul>

<h2>3. Editing mutes</h2>
<ul>
  <li><b>Click</b> a checkbox to toggle one mic.</li>
  <li><b>Drag</b> a rectangle across cells to select a block (multiple cues ×
      multiple mics).</li>
  <li>Then use <b>Unmute selected / Mute selected / Toggle selected</b>, the
      right-click menu, or the keyboard:
      <kbd>Space</kbd> toggles, <kbd>1</kbd> unmutes, <kbd>0</kbd> mutes.</li>
  <li><b>Select all</b> selects the whole grid (e.g. mute everything, then open
      just the mics you need).</li>
</ul>

<h2>4. Undo</h2>
<p><kbd>⌘Z</kbd> (or the <b>Undo</b> button) reverses the last <b>30</b> actions
— checkbox changes and name edits.</p>

<h2>5. Naming mics (e.g. actor/role names)</h2>
<p>Double-click a mic's <b>column header</b>, or use <b>Mic names…</b>. A name
does three things when you Submit:</p>
<ul>
  <li>Labels that column in QLab Flash.</li>
  <li>Renames that mic's cue everywhere it appears in QLab.</li>
  <li>Sets the channel name on the <b>X32 scribble strip</b> — if you've entered
      the mixer's IP under <b>Mixer…</b>.</li>
</ul>
<p class="tip">Set the X32's IP once in <b>Mixer…</b> to enable scribble-strip
updates; leave it blank to skip that part.</p>

<h2>6. Renaming cues</h2>
<p><b>Double-click any cue or group name</b> in the left column to rename it.
Changes are pushed to QLab on Submit.</p>

<h2>7. Views</h2>
<ul>
  <li><b>Collapse to cues</b> — one row per mic cue with its 32 checkboxes.</li>
  <li><b>Expand all</b> — the full QLab hierarchy.</li>
</ul>

<h2>8. Submitting</h2>
<ul>
  <li><b>Submit changes to QLab</b> — sends only what you changed (mic states,
      cue names, mixer names).</li>
  <li><b>Submit ALL mics</b> — rewrites every mic in every cue (plus any name
      edits). Useful for a full re-sync.</li>
  <li><b>Reload</b> re-reads everything fresh from QLab.</li>
</ul>

<h2>9. How your QLab cues must be built</h2>
<p>QLab Flash works with X32 <b>channel On/Off</b> network cues that target a
<b>specific channel number</b> (e.g. <code>/ch/01/mix/on</code>). Tips:</p>
<ul>
  <li>Set each cue's <b>Channel</b> to a concrete number (01–32), not the
      <code>{channel}</code> placeholder — otherwise QLab Flash can't tell which
      mic it is.</li>
  <li>Typically every cue (look) contains all 32 channel cues, often grouped in
      a "Mics" group. Any nesting depth works.</li>
</ul>

<h2>10. Troubleshooting</h2>
<ul>
  <li><b>No checkboxes appear:</b> your cues may use the <code>{channel}</code>
      placeholder — set concrete channel numbers, then Reload.</li>
  <li><b>"denied" in the OSC log:</b> grant OSC access (view/control) in QLab's
      Workspace Settings → Network.</li>
  <li><b>Show OSC log</b> reveals exactly what's sent/received.</li>
  <li><b>Diagnose…</b> inspects a single cue's QLab properties.</li>
</ul>
"""
