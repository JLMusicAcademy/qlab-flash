import struct

from qlabflash import osc


def test_encode_address_only():
    data = osc.encode_message("/go")
    # "/go\0" = 4 bytes, then ",\0\0\0" type tag = 4 bytes
    assert data == b"/go\x00" + b",\x00\x00\x00"


def test_roundtrip_string_arg():
    data = osc.encode_message("/cue_id/abc/customString", "/ch/01/mix/on 1")
    addr, args = osc.decode_message(data)
    assert addr == "/cue_id/abc/customString"
    assert args == ["/ch/01/mix/on 1"]


def test_roundtrip_mixed_args():
    data = osc.encode_message("/test", 7, 1.5, "hi")
    addr, args = osc.decode_message(data)
    assert addr == "/test"
    assert args[0] == 7
    assert abs(args[1] - 1.5) < 1e-6
    assert args[2] == "hi"


def test_string_padding_alignment():
    # "/go" -> needs padding to 4 bytes; "abcd" -> needs an extra 4-byte block.
    for s in ["a", "ab", "abc", "abcd", "abcde"]:
        data = osc.encode_message("/x", s)
        assert len(data) % 4 == 0
        _, args = osc.decode_message(data)
        assert args == [s]


def test_decode_bundle():
    m1 = osc.encode_message("/one", 1)
    m2 = osc.encode_message("/two", "x")
    bundle = bytearray(b"#bundle\x00")
    bundle += struct.pack(">Q", 1)  # timetag
    for m in (m1, m2):
        bundle += struct.pack(">i", len(m)) + m
    messages = osc.decode_packet(bytes(bundle))
    assert messages[0] == ("/one", [1])
    assert messages[1] == ("/two", ["x"])


def test_bool_encoded_as_int():
    data = osc.encode_message("/b", True, False)
    _, args = osc.decode_message(data)
    assert args == [1, 0]


def test_slip_roundtrip_with_escapes():
    # Payload deliberately contains END (0xC0) and ESC (0xDB) bytes.
    payload = bytes([0x01, osc.SLIP_END, 0x02, osc.SLIP_ESC, 0x03])
    framed = osc.slip_encode(payload)
    assert framed[0] == osc.SLIP_END and framed[-1] == osc.SLIP_END
    decoder = osc.SlipDecoder()
    assert decoder.feed(framed) == [payload]


def test_slip_decoder_handles_split_and_multiple_frames():
    p1 = osc.encode_message("/one", 1)
    p2 = osc.encode_message("/two", "hello")
    stream = osc.slip_encode(p1) + osc.slip_encode(p2)
    decoder = osc.SlipDecoder()
    out = []
    # Feed the stream one byte at a time to exercise buffering.
    for b in stream:
        out.extend(decoder.feed(bytes([b])))
    assert [osc.decode_message(p) for p in out] == [
        ("/one", [1]), ("/two", ["hello"])]
