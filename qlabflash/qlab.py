"""A small QLab OSC client (TCP or UDP).

Talks to QLab using its OSC dictionary. Most QLab queries generate a reply: a
single OSC message whose only argument is a JSON string of the form::

    {"workspace_id": "...", "address": "/the/method", "status": "ok",
     "data": <whatever was requested>}

We send a query, then wait for the reply whose JSON ``address`` matches the
method we asked about. Replies are matched on the *suffix* of the address so we
don't have to care whether QLab echoes the workspace prefix back.

Transport: TCP is the default and is *required* for methods that return large
replies (e.g. ``/cueLists`` on a real show) — those easily exceed the maximum
size of a single UDP datagram, so QLab itself tells you to use TCP for them.
Over TCP, packets are framed with double-END SLIP (RFC 1055) and QLab sends
replies back on the same connection. UDP remains available for simple setups.

Threading: a single background thread drains the socket and dispatches each
reply to the waiting caller via a per-key queue.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from typing import Any, Dict, List, Optional

from . import osc


class QLabError(RuntimeError):
    pass


class QLabClient:
    def __init__(self, host: str, port: int = 53000, transport: str = "tcp",
                 listen_port: int = 0, reply_timeout: float = 5.0,
                 connect_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.transport = transport.lower()
        self.reply_timeout = reply_timeout

        self._lock = threading.Lock()
        self._waiters: Dict[str, "queue.Queue[Any]"] = {}
        self._log_cb = None

        if self.transport == "tcp":
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(connect_timeout)
            self._sock.connect((host, port))
            self._sock.settimeout(None)
            self._slip = osc.SlipDecoder()
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("", listen_port))
            self.listen_port = self._sock.getsockname()[1]

        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    # -- public API ---------------------------------------------------------
    def set_logger(self, callback) -> None:
        """Register ``callback(direction, address, detail)`` for traffic logging."""
        self._log_cb = callback

    def close(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    def send(self, address: str, *args: Any) -> None:
        """Fire-and-forget OSC message."""
        packet = osc.encode_message(address, *args)
        if self.transport == "tcp":
            self._sock.sendall(osc.slip_encode(packet))
        else:
            self._sock.sendto(packet, (self.host, self.port))
        self._log("send", address, list(args))

    def query(self, address: str, *args: Any,
              match_suffix: Optional[str] = None,
              timeout: Optional[float] = None) -> Any:
        """Send ``address`` and return the ``data`` field of its reply.

        ``match_suffix`` is the address suffix used to pair the reply with this
        request; it defaults to ``address``. Raises :class:`QLabError` on
        timeout or a non-ok status.
        """
        key = match_suffix or address
        q: "queue.Queue[Any]" = queue.Queue(maxsize=1)
        with self._lock:
            self._waiters[key] = q
        try:
            self.send(address, *args)
            try:
                reply = q.get(timeout=timeout or self.reply_timeout)
            except queue.Empty:
                raise QLabError(f"Timed out waiting for reply to {address}")
        finally:
            with self._lock:
                self._waiters.pop(key, None)

        status = reply.get("status", "ok")
        if status not in ("ok", "denied:no-passcode-required", None):
            # ``denied`` etc. are still returned to the caller to inspect.
            pass
        return reply.get("data"), status

    # -- high level QLab methods -------------------------------------------
    def workspaces(self) -> List[dict]:
        data, _ = self.query("/workspaces")
        return data or []

    def connect_workspace(self, workspace_id: str, passcode: str = "") -> str:
        addr = f"/workspace/{workspace_id}/connect"
        args = (passcode,) if passcode else ()
        # Match on the "/connect" suffix so it works whether or not QLab echoes
        # the workspace prefix back in the reply's address field.
        data, status = self.query(addr, *args, match_suffix="/connect")
        # QLab returns data like "ok", "badpass", or a permission string.
        return data if isinstance(data, str) else status

    def cue_lists(self, workspace_id: str) -> List[dict]:
        addr = f"/workspace/{workspace_id}/cueLists"
        data, _ = self.query(addr, match_suffix="/cueLists")
        return data or []

    def cue_property(self, workspace_id: str, cue_uid: str,
                     prop: str) -> Optional[str]:
        addr = f"/workspace/{workspace_id}/cue_id/{cue_uid}/{prop}"
        try:
            data, _ = self.query(addr, match_suffix=f"/cue_id/{cue_uid}/{prop}")
        except QLabError:
            return None
        if data is None:
            return None
        return str(data)

    def get_cue_properties(self, workspace_id: str, cue_uids: List[str],
                           prop: str, chunk_size: int = 48,
                           timeout: Optional[float] = None) -> Dict[str, Optional[str]]:
        """Fetch ``prop`` for many cues, pipelining requests for speed.

        Sending all queries up front and then collecting replies avoids paying
        a full round-trip latency per cue, which matters for shows with
        thousands of mic cues. Requests are sent in chunks to avoid flooding
        the UDP socket. Missing replies come back as ``None``.
        """
        results: Dict[str, Optional[str]] = {}
        for start in range(0, len(cue_uids), chunk_size):
            chunk = cue_uids[start:start + chunk_size]
            waiters: Dict[str, queue.Queue] = {}
            with self._lock:
                for uid in chunk:
                    key = f"/cue_id/{uid}/{prop}"
                    q: "queue.Queue[Any]" = queue.Queue(maxsize=1)
                    self._waiters[key] = q
                    waiters[uid] = q
            for uid in chunk:
                self.send(f"/workspace/{workspace_id}/cue_id/{uid}/{prop}")
            deadline = time.time() + (timeout or self.reply_timeout)
            for uid, q in waiters.items():
                remaining = max(0.0, deadline - time.time())
                try:
                    reply = q.get(timeout=remaining)
                    data = reply.get("data")
                    results[uid] = None if data is None else str(data)
                except queue.Empty:
                    results[uid] = None
                finally:
                    with self._lock:
                        self._waiters.pop(f"/cue_id/{uid}/{prop}", None)
        return results

    def set_cue_property(self, workspace_id: str, cue_uid: str,
                         prop: str, value: str) -> None:
        # Setting a property is fire-and-forget; QLab applies it immediately.
        addr = f"/workspace/{workspace_id}/cue_id/{cue_uid}/{prop}"
        self.send(addr, value)

    def probe_cue(self, workspace_id: str, cue_uid: str, keys,
                  timeout: float = 2.0):
        """Query many property ``keys`` of one cue at once (diagnostic).

        Returns ``{key: (status, data)}`` where data is None / missing if the
        property doesn't exist. Used to discover how a cue stores its values.
        """
        results = {}
        waiters = {}
        with self._lock:
            for k in keys:
                wkey = f"/cue_id/{cue_uid}/{k}"
                q: "queue.Queue[Any]" = queue.Queue(maxsize=1)
                self._waiters[wkey] = q
                waiters[k] = q
        for k in keys:
            self.send(f"/workspace/{workspace_id}/cue_id/{cue_uid}/{k}")
        deadline = time.time() + timeout
        for k, q in waiters.items():
            remaining = max(0.0, deadline - time.time())
            try:
                reply = q.get(timeout=remaining)
                results[k] = (reply.get("status"), reply.get("data"))
            except queue.Empty:
                results[k] = ("(no reply)", None)
            finally:
                with self._lock:
                    self._waiters.pop(f"/cue_id/{cue_uid}/{k}", None)
        return results

    # -- internals ----------------------------------------------------------
    def _recv_loop(self) -> None:
        if self.transport == "tcp":
            self._recv_loop_tcp()
        else:
            self._recv_loop_udp()

    def _recv_loop_udp(self) -> None:
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(65535)
            except OSError:
                break
            for address, args in osc.decode_packet(data):
                self._dispatch(address, args)

    def _recv_loop_tcp(self) -> None:
        while self._running:
            try:
                data = self._sock.recv(65535)
            except OSError:
                break
            if not data:
                break  # QLab closed the connection
            for packet in self._slip.feed(data):
                for address, args in osc.decode_packet(packet):
                    self._dispatch(address, args)

    def _dispatch(self, address: str, args: List[Any]) -> None:
        payload = args[0] if args else None
        reply: Dict[str, Any]
        if isinstance(payload, str):
            try:
                reply = json.loads(payload)
            except json.JSONDecodeError:
                reply = {"address": address, "data": payload, "status": "ok"}
        else:
            reply = {"address": address, "data": payload, "status": "ok"}

        reply_addr = reply.get("address", address)
        self._log("recv", reply_addr, reply.get("status"))

        # Match the waiter whose key is a suffix of this reply's address.
        with self._lock:
            match_key = None
            for key in self._waiters:
                if reply_addr == key or reply_addr.endswith(key):
                    match_key = key
                    break
            waiter = self._waiters.get(match_key) if match_key else None
        if waiter is not None:
            try:
                waiter.put_nowait(reply)
            except queue.Full:
                pass

    def _log(self, direction: str, address: str, detail: Any) -> None:
        if self._log_cb is not None:
            try:
                self._log_cb(direction, address, detail)
            except Exception:
                pass
