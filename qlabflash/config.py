"""Application configuration.

Everything that might differ between QLab versions, console models, or studio
conventions lives here so it can be changed without touching code. The defaults
target QLab 5 driving a Behringer X32 using channel-on as the mute control.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

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
    listen_port: int = 53001        # Local port we bind for sending/receiving.
    passcode: str = ""              # QLab 5 workspace passcode, if any.

    # --- Mic grid ----------------------------------------------------------
    mic_count: int = 32

    # --- How mic state is stored in QLab cues ------------------------------
    # The QLab cue property that holds a network cue's outgoing OSC text. This
    # has historically been "customString". If your QLab build reports the
    # message under a different property, change it here.
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
