"""Application configuration.

Everything that might differ between QLab versions, console models, or studio
conventions lives here so it can be changed without touching code. The defaults
target QLab 5 driving a Behringer X32 using channel-on as the mute control.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict

# X32 channel-on OSC command. On the X32, ``/ch/NN/mix/on`` with argument 1
# means the channel is ON (audible / unmuted) and 0 means OFF (muted). This
# matches the user's convention: a checked box = unmuted.
DEFAULT_CHANNEL_PATTERN = r"^\s*/ch/0*(?P<chan>\d{1,2})/mix/on(?:\s+(?P<state>\d+))?\s*$"
DEFAULT_WRITE_TEMPLATE = "/ch/{chan:02d}/mix/on {state}"


@dataclass
class Config:
    # --- Network -----------------------------------------------------------
    qlab_host: str = "127.0.0.1"
    qlab_port: int = 53000          # QLab's fixed OSC receive port.
    # TCP is required for reading cue lists on real shows: those replies are
    # bigger than a single UDP datagram can hold. UDP is left as an option.
    transport: str = "tcp"
    listen_port: int = 0            # UDP-only: local port to bind (0 = any).
    passcode: str = ""              # QLab 5 workspace passcode, if any.

    # --- Mic grid ----------------------------------------------------------
    mic_count: int = 32

    # --- X32 mixer (for scribble-strip channel names) ----------------------
    # The mixer's IP, so renaming a mic can also set the channel name on the
    # console. Blank disables scribble-strip updates. The X32 listens on 10023.
    x32_host: str = ""
    x32_port: int = 10023
    scribble_template: str = "/ch/{chan:02d}/config/name"

    # Friendly per-mic names shown in the column headers, e.g. {"1": "Doug"}.
    # Keyed by channel number (as a string, since JSON object keys are strings).
    # Purely a display aid — it never changes anything in QLab.
    channel_labels: Dict[str, str] = field(default_factory=dict)

    # --- How mic state is stored in QLab cues ------------------------------
    # The QLab cue property the app reads to determine each mic's state. QLab 5
    # X32 "network audio" cues expose their value as a structured list under
    # "parameterValues" (e.g. ['ch', 1, 'mix', 'on', 0]). Older / custom-OSC
    # setups instead store a text message under "customString" — set this to
    # "customString" for those.
    read_property: str = "parameterValues"

    # Property used to WRITE back a text OSC message (only for custom-OSC cues,
    # i.e. when a cue isn't a structured parameterValues cue).
    osc_message_property: str = "customString"

    # Regex used to recognise a mic cue and pull out the channel number and its
    # current on/off state from the cue's OSC message text. Must define named
    # groups ``chan`` and (optionally) ``state``.
    channel_pattern: str = DEFAULT_CHANNEL_PATTERN

    # Template used to write a mic cue's OSC message text back out. ``chan`` is
    # the 1-based channel number, ``state`` is unmuted_value or muted_value.
    write_template: str = DEFAULT_WRITE_TEMPLATE

    unmuted_value: int = 1          # OSC arg value that means "unmuted".
    muted_value: int = 0            # OSC arg value that means "muted".

    # --- Misc --------------------------------------------------------------
    reply_timeout: float = 5.0      # Seconds to wait for a QLab reply.

    def channel_state_value(self, unmuted: bool) -> int:
        return self.unmuted_value if unmuted else self.muted_value

    def is_unmuted_value(self, value: int) -> bool:
        return value == self.unmuted_value

    # --- Mic names ---------------------------------------------------------
    def label_for(self, channel: int) -> str:
        return self.channel_labels.get(str(channel), "")

    def set_label(self, channel: int, name: str) -> None:
        name = (name or "").strip()
        if name:
            self.channel_labels[str(channel)] = name
        else:
            self.channel_labels.pop(str(channel), None)

    def has_labels(self) -> bool:
        return any(v.strip() for v in self.channel_labels.values())

    def header_text(self, channel: int) -> str:
        """Column header text: the name if set, otherwise the number."""
        return self.label_for(channel) or str(channel)

    # --- Persistence -------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Config":
        if not path or not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
            fh.write("\n")
