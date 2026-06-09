"""A mock QLab OSC server.

It speaks just enough of QLab's OSC dictionary to exercise the whole app
(discover workspace -> connect -> read cues -> read/write mic state) without a
real copy of QLab. Used by the test-suite and by the GUI's "Demo" mode so the
interface can be driven on any machine.

The simulated show: one cue list with several "look" group cues, each holding
32 Network cues that send ``/ch/NN/mix/on {0|1}`` to an X32.
"""

from __future__ import annotations

import json
import socket
import threading
from typing import Dict, List

from . import osc

WORKSPACE_ID = "mock-ws-1"


def _make_show(num_looks: int = 6, mic_count: int = 32):
    """Build the cue tree and the per-cue OSC message text store."""
    cue_lists: List[dict] = []
    texts: Dict[str, str] = {}

    list_cues = []
    for look in range(1, num_looks + 1):
        # 32 mic cues live inside a nested "Mics" group, mirroring a typical
        # show: Cue N (group) -> { Mics (group of 32), Audio, Lights, Video }.
        mic_children = []
        for chan in range(1, mic_count + 1):
            uid = f"net-{look}-{chan}"
            # Open mics: a rotating handful per look, everything else muted.
            on = 1 if (chan % num_looks) == (look % num_looks) else 0
            texts[uid] = f"/ch/{chan:02d}/mix/on {on}"
            mic_children.append({
                "uniqueID": uid,
                "number": f"{look}.{chan}",
                "name": f"Ch {chan} {'ON' if on else 'OFF'}",
                "type": "Network",
            })
        mics_group = {
            "uniqueID": f"mics-{look}",
            "number": "",
            "name": "Mics",
            "type": "Group",
            "cues": mic_children,
        }
        # Non-mic siblings inside the cue group (must be ignored by the grid).
        siblings = [
            {"uniqueID": f"aud-{look}", "number": "", "name": "Audio",
             "type": "Audio"},
            {"uniqueID": f"lx-{look}", "number": "", "name": "Lights",
             "type": "Network"},
        ]
        texts[f"lx-{look}"] = "/eos/chan/1/out 100"  # non-mic OSC, won't match
        list_cues.append({
            "uniqueID": f"group-{look}",
            "number": str(look),
            "name": f"Cue {look}",
            "type": "Group",
            "cues": [mics_group] + siblings,
        })
        # A standalone non-group cue sprinkled between cues (should be hidden,
        # since it has no mics).
        list_cues.append({
            "uniqueID": f"note-{look}",
            "number": "",
            "name": f"Note {look}",
            "type": "Memo",
        })

    cue_lists.append({
        "uniqueID": "cuelist-main",
        "number": "",
        "name": "Main Cue List",
        "listName": "Main Cue List",
        "type": "Cue List",
        "cues": list_cues,
    })
    return cue_lists, texts


class MockQLab:
    def __init__(self, host: str = "127.0.0.1", port: int = 53000,
                 num_looks: int = 6, mic_count: int = 32):
        self.cue_lists, self.texts = _make_show(num_looks, mic_count)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self.port = self._sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    def _reply(self, dest, address: str, data, status: str = "ok") -> None:
        payload = json.dumps({
            "workspace_id": WORKSPACE_ID,
            "address": address,
            "status": status,
            "data": data,
        })
        self._sock.sendto(osc.encode_message(address, payload), dest)

    def _loop(self) -> None:
        while self._running:
            try:
                data, src = self._sock.recvfrom(65535)
            except OSError:
                break
            try:
                address, args = osc.decode_message(data)
            except Exception:
                continue
            self._handle(src, address, args)

    def _handle(self, src, address: str, args: List) -> None:
        if address == "/workspaces":
            self._reply(src, "/workspaces", [{
                "uniqueID": WORKSPACE_ID,
                "displayName": "Mock Show.qlab5",
                "hasPasscode": False,
                "version": "5.5.0",
            }])
            return

        if address.endswith("/connect"):
            self._reply(src, address, "ok")
            return

        if address.endswith("/cueLists"):
            self._reply(src, address, self.cue_lists)
            return

        # /workspace/{id}/cue_id/{uid}/{prop}
        parts = address.split("/cue_id/")
        if len(parts) == 2:
            uid, _, prop = parts[1].partition("/")
            if args:  # set
                self.texts[uid] = str(args[0])
                # QLab acknowledges sets too; harmless if the client ignores it.
                self._reply(src, address, self.texts[uid])
            else:      # get
                self._reply(src, address, self.texts.get(uid, ""))
            return
