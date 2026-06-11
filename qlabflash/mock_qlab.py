"""A mock QLab OSC server.

It speaks just enough of QLab's OSC dictionary to exercise the whole app
(discover workspace -> connect -> read cues -> read/write mic state) without a
real copy of QLab. Used by the test-suite and by the GUI's "Demo" mode so the
interface can be driven on any machine.

The simulated show: one cue list with several group cues, each holding 32
Network cues that send ``/ch/NN/mix/on {0|1}`` to an X32.
"""

from __future__ import annotations

import json
import socket
import threading
from typing import Dict, List

from . import osc

WORKSPACE_ID = "mock-ws-1"


def _make_show(num_cues: int = 6, mic_count: int = 32):
    """Build the cue tree and the per-cue OSC message text store."""
    cue_lists: List[dict] = []
    texts: Dict[str, str] = {}

    list_cues = []
    for cue in range(1, num_cues + 1):
        # 32 mic cues live inside a nested "Mics" group, mirroring a typical
        # show: Cue N (group) -> { Mics (group of 32), Audio, Lights, Video }.
        mic_children = []
        for chan in range(1, mic_count + 1):
            uid = f"net-{cue}-{chan}"
            # Open mics: a rotating handful per cue, everything else muted.
            on = 1 if (chan % num_cues) == (cue % num_cues) else 0
            texts[uid] = f"/ch/{chan:02d}/mix/on {on}"
            mic_children.append({
                "uniqueID": uid,
                "number": f"{cue}.{chan}",
                "name": f"Ch {chan} {'ON' if on else 'OFF'}",
                "type": "Network",
            })
        mics_group = {
            "uniqueID": f"mics-{cue}",
            "number": "",
            "name": "Mics",
            "type": "Group",
            "cues": mic_children,
        }
        # Non-mic siblings inside the cue group (must be ignored by the grid).
        siblings = [
            {"uniqueID": f"aud-{cue}", "number": "", "name": "Audio",
             "type": "Audio"},
            {"uniqueID": f"lx-{cue}", "number": "", "name": "Lights",
             "type": "Network"},
        ]
        texts[f"lx-{cue}"] = "/eos/chan/1/out 100"  # non-mic OSC, won't match
        list_cues.append({
            "uniqueID": f"group-{cue}",
            "number": str(cue),
            "name": f"Cue {cue}",
            "type": "Group",
            "cues": [mics_group] + siblings,
        })
        # A standalone non-group cue sprinkled between cues (should be hidden,
        # since it has no mics).
        list_cues.append({
            "uniqueID": f"note-{cue}",
            "number": "",
            "name": f"Note {cue}",
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

    # Index every cue dict by uid so set-name can mutate the live tree.
    index = {}

    def _index(node):
        index[node["uniqueID"]] = node
        for child in node.get("cues", []):
            _index(child)

    for cl in cue_lists:
        _index(cl)
    return cue_lists, texts, index


class MockQLab:
    """A simulated QLab. Defaults to TCP (like the real app); supports UDP too."""

    def __init__(self, host: str = "127.0.0.1", port: int = 53000,
                 transport: str = "tcp", num_cues: int = 6, mic_count: int = 32):
        self.cue_lists, self.texts, self._index = _make_show(num_cues, mic_count)
        self.transport = transport.lower()
        self._running = True

        if self.transport == "tcp":
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((host, port))
            self._sock.listen(5)
            self.port = self._sock.getsockname()[1]
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((host, port))
            self.port = self._sock.getsockname()[1]
            self._thread = threading.Thread(target=self._udp_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    @staticmethod
    def _packet(address: str, data, status: str = "ok") -> bytes:
        payload = json.dumps({
            "workspace_id": WORKSPACE_ID,
            "address": address,
            "status": status,
            "data": data,
        })
        return osc.encode_message(address, payload)

    # -- UDP -----------------------------------------------------------------
    def _udp_loop(self) -> None:
        while self._running:
            try:
                data, src = self._sock.recvfrom(65535)
            except OSError:
                break
            try:
                address, args = osc.decode_message(data)
            except Exception:
                continue
            self._handle(lambda pkt: self._sock.sendto(pkt, src), address, args)

    # -- TCP -----------------------------------------------------------------
    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve_conn, args=(conn,),
                             daemon=True).start()

    def _serve_conn(self, conn) -> None:
        decoder = osc.SlipDecoder()
        send = lambda pkt: conn.sendall(osc.slip_encode(pkt))
        try:
            while self._running:
                data = conn.recv(65535)
                if not data:
                    break
                for packet in decoder.feed(data):
                    try:
                        address, args = osc.decode_message(packet)
                    except Exception:
                        continue
                    self._handle(send, address, args)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # -- request handling (transport-agnostic) ------------------------------
    def _handle(self, send, address: str, args: List) -> None:
        try:
            if address == "/workspaces":
                send(self._packet("/workspaces", [{
                    "uniqueID": WORKSPACE_ID,
                    "displayName": "Mock Show.qlab5",
                    "hasPasscode": False,
                    "version": "5.5.0",
                }]))
                return

            if address.endswith("/connect"):
                send(self._packet(address, "ok"))
                return

            if address.endswith("/cueLists"):
                send(self._packet(address, self.cue_lists))
                return

            # /workspace/{id}/cue_id/{uid}/{prop}
            parts = address.split("/cue_id/")
            if len(parts) == 2:
                uid, _, prop = parts[1].partition("/")
                if args:  # set
                    value = str(args[0])
                    if prop == "name" and uid in self._index:
                        self._index[uid]["name"] = value
                    else:
                        self.texts[uid] = value
                    send(self._packet(address, value))
                else:      # get
                    if prop == "name":
                        node = self._index.get(uid, {})
                        send(self._packet(address, node.get("name", "")))
                    else:
                        send(self._packet(address, self.texts.get(uid, "")))
                return
        except OSError:
            pass  # client went away mid-reply; ignore
