"""Minimal, dependency-free OSC 1.0 encoder/decoder.

QLab speaks OSC over UDP. We only need a small slice of the spec:

* Encode outgoing messages with int / float / string arguments.
* Decode incoming messages and bundles. QLab's replies arrive as a single
  OSC message whose only argument is a JSON string, so robust string decoding
  is the important part.

Implementing this directly (rather than depending on python-osc) keeps the
install footprint tiny and gives us full control over how QLab replies are
parsed.
"""

from __future__ import annotations

import struct
from typing import Any, List, Tuple

BUNDLE_PREFIX = b"#bundle\x00"


def _pad(data: bytes) -> bytes:
    """Pad ``data`` with NUL bytes to the next 4-byte boundary."""
    remainder = len(data) % 4
    if remainder == 0:
        return data
    return data + b"\x00" * (4 - remainder)


def _encode_string(value: str) -> bytes:
    """Encode an OSC string: UTF-8 bytes, NUL terminated, 4-byte aligned."""
    return _pad(value.encode("utf-8") + b"\x00")


def encode_message(address: str, *args: Any) -> bytes:
    """Encode an OSC message.

    Supported argument types: ``int`` -> int32 (``i``), ``float`` -> float32
    (``f``), ``str`` -> string (``s``), ``bytes`` -> blob (``b``).
    """
    out = bytearray()
    out += _encode_string(address)

    type_tags = ","
    payload = bytearray()
    for arg in args:
        if isinstance(arg, bool):
            # bool is a subclass of int; OSC has no bool, send as int32.
            type_tags += "i"
            payload += struct.pack(">i", 1 if arg else 0)
        elif isinstance(arg, int):
            type_tags += "i"
            payload += struct.pack(">i", arg)
        elif isinstance(arg, float):
            type_tags += "f"
            payload += struct.pack(">f", arg)
        elif isinstance(arg, str):
            type_tags += "s"
            payload += _encode_string(arg)
        elif isinstance(arg, (bytes, bytearray)):
            type_tags += "b"
            payload += struct.pack(">i", len(arg)) + _pad(bytes(arg))
        else:
            raise TypeError(f"Unsupported OSC argument type: {type(arg)!r}")

    out += _encode_string(type_tags)
    out += payload
    return bytes(out)


def _read_string(data: bytes, offset: int) -> Tuple[str, int]:
    end = data.index(b"\x00", offset)
    value = data[offset:end].decode("utf-8", errors="replace")
    # Advance past the string and its 4-byte alignment padding.
    length = end - offset + 1
    padded = length + (-length % 4)
    return value, offset + padded


def _read_blob(data: bytes, offset: int) -> Tuple[bytes, int]:
    (size,) = struct.unpack_from(">i", data, offset)
    offset += 4
    blob = data[offset:offset + size]
    padded = size + (-size % 4)
    return blob, offset + padded


def decode_message(data: bytes, offset: int = 0) -> Tuple[str, List[Any]]:
    """Decode a single OSC *message* (not a bundle).

    Returns ``(address, args)``.
    """
    address, offset = _read_string(data, offset)
    if offset >= len(data):
        return address, []

    type_tags, offset = _read_string(data, offset)
    if not type_tags.startswith(","):
        # No (valid) type tag string; treat as argument-less message.
        return address, []

    args: List[Any] = []
    for tag in type_tags[1:]:
        if tag == "i":
            (value,) = struct.unpack_from(">i", data, offset)
            offset += 4
            args.append(value)
        elif tag == "f":
            (value,) = struct.unpack_from(">f", data, offset)
            offset += 4
            args.append(value)
        elif tag == "s":
            value, offset = _read_string(data, offset)
            args.append(value)
        elif tag == "b":
            value, offset = _read_blob(data, offset)
            args.append(value)
        elif tag in ("T", "F"):
            args.append(tag == "T")
        elif tag == "N":
            args.append(None)
        else:
            # Unknown tag: we can't know its width, so stop parsing safely.
            break
    return address, args


def decode_packet(data: bytes) -> List[Tuple[str, List[Any]]]:
    """Decode an OSC packet, which may be a single message or a bundle.

    Returns a flat list of ``(address, args)`` messages.
    """
    if data.startswith(BUNDLE_PREFIX):
        return _decode_bundle(data)
    return [decode_message(data)]


def _decode_bundle(data: bytes) -> List[Tuple[str, List[Any]]]:
    messages: List[Tuple[str, List[Any]]] = []
    # 8 bytes "#bundle\0" + 8 bytes timetag, then size-prefixed elements.
    offset = 16
    while offset < len(data):
        (size,) = struct.unpack_from(">i", data, offset)
        offset += 4
        element = data[offset:offset + size]
        offset += size
        if element.startswith(BUNDLE_PREFIX):
            messages.extend(_decode_bundle(element))
        else:
            messages.append(decode_message(element))
    return messages
