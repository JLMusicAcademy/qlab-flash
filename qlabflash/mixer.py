"""Send OSC directly to a Behringer X32 mixer (e.g. scribble-strip names).

QLab Flash normally talks to QLab, but the X32's channel *name* (the scribble
strip) is a live mixer setting, so we send `/ch/NN/config/name "Annie"` straight
to the console over UDP (port 10023 by default).
"""

from __future__ import annotations

import socket
from typing import Iterable, Tuple

from . import osc


def send_scribble_names(host: str, port: int, template: str,
                        names: Iterable[Tuple[int, str]]) -> int:
    """Set channel names on the X32. Returns how many were sent.

    ``names`` is ``(channel, name)`` pairs. Does nothing (returns 0) if no host
    is configured. Network errors are swallowed so a mixer that's off/unreachable
    never blocks a submit.
    """
    host = (host or "").strip()
    names = list(names)
    if not host or not names:
        return 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    try:
        for chan, name in names:
            address = template.format(chan=chan)
            try:
                sock.sendto(osc.encode_message(address, name), (host, port))
                sent += 1
            except OSError:
                pass
    finally:
        sock.close()
    return sent
