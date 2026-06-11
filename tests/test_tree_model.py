"""Tests for the dynamic anchor-cue detection at arbitrary nesting depths."""

from qlabflash.config import Config
from qlabflash.model import Cue, GridModel


def grp(uid, name, *children, number=""):
    return Cue(uid=uid, number=number, name=name, type="Group",
               children=list(children))


def mic(uid, chan, on=1):
    # A network cue; its text is provided via the texts dict in tests.
    return Cue(uid=uid, number="", name=f"Ch {chan}", type="Network")


def build(top, texts, mic_count=8):
    m = GridModel(Config(mic_count=mic_count))
    m.build_tree(top, lambda uid: texts.get(uid))
    return m


def test_mics_direct_in_cue():
    top = [grp("c1", "Cue 1", mic("m1", 1), mic("m2", 2))]
    texts = {"m1": "/ch/01/mix/on 1", "m2": "/ch/02/mix/on 0"}
    m = build(top, texts)
    anchors = m.anchors()
    assert [a.uid for a in anchors] == ["c1"]
    assert set(anchors[0].cells) == {1, 2}


def test_cue_then_mics_group():
    top = [grp("c1", "Cue 1", grp("mg", "Mics", mic("m1", 1), mic("m2", 2)))]
    texts = {"m1": "/ch/01/mix/on 1", "m2": "/ch/02/mix/on 1"}
    m = build(top, texts)
    assert [a.uid for a in m.anchors()] == ["c1"]   # the Cue, not the Mics group


def test_three_levels_deep():
    top = [grp("c1", "Cue 1",
               grp("g2", "Stuff",
                   grp("mg", "Mics", mic("m1", 1), mic("m2", 2))))]
    texts = {"m1": "/ch/01/mix/on 1", "m2": "/ch/02/mix/on 1"}
    m = build(top, texts)
    assert [a.uid for a in m.anchors()] == ["c1"]


def test_act_spanning_two_cues_splits_into_two_cues():
    # Act 1 contains Cue 1 and Cue 2, each with its own Ch1/Ch2. The Act has
    # duplicate channels, so it must NOT be an anchor; the two cues each carry checkboxes.
    top = [grp("act", "Act 1",
               grp("c1", "Cue 1", mic("m1a", 1), mic("m2a", 2)),
               grp("c2", "Cue 2", mic("m1b", 1), mic("m2b", 2)))]
    texts = {"m1a": "/ch/01/mix/on 1", "m2a": "/ch/02/mix/on 0",
             "m1b": "/ch/01/mix/on 0", "m2b": "/ch/02/mix/on 1"}
    m = build(top, texts)
    anchors = m.anchors()
    assert [a.uid for a in anchors] == ["c1", "c2"]
    # The Act node itself is not an anchor and shows no checkboxes.
    act = m.roots[0]
    assert act.uid == "act" and not act.is_anchor and act.cells == {}


def test_mic_leaf_shares_cell_with_its_anchor():
    top = [grp("c1", "Cue 1", grp("mg", "Mics", mic("m1", 1)))]
    texts = {"m1": "/ch/01/mix/on 1"}
    m = build(top, texts)
    anchor = m.anchors()[0]
    leaf = [n for n in m.iter_rows() if n.uid == "m1"][0]
    # The leaf's own box and the anchor's aggregated box are the SAME object,
    # so editing one is reflected in the other.
    assert anchor.cells[1] is leaf.cells[1]
    anchor.cells[1].unmuted = False
    assert leaf.cells[1].unmuted is False


def test_non_mic_cues_are_blank():
    top = [grp("c1", "Cue 1", mic("m1", 1)),
           Cue(uid="audio", number="", name="Sound", type="Audio")]
    texts = {"m1": "/ch/01/mix/on 1"}
    m = build(top, texts)
    audio = [n for n in m.iter_rows() if n.uid == "audio"][0]
    assert audio.cells == {} and not audio.is_anchor


def test_name_edits_tracked_and_written():
    top = [grp("c1", "Cue 1", mic("m1", 1))]
    texts = {"m1": "/ch/01/mix/on 1"}
    m = build(top, texts)
    node = m.roots[0]
    assert m.name_dirty_count() == 0
    node.name = "Top of Act 1"
    assert node.name_dirty
    assert m.name_writes() == [("c1", "name", "Top of Act 1")]
    assert m.name_dirty_count() == 1
    m.mark_committed()
    assert m.name_dirty_count() == 0


def test_mic_writes_only_dirty():
    top = [grp("c1", "Cue 1", mic("m1", 1), mic("m2", 2))]
    texts = {"m1": "/ch/01/mix/on 1", "m2": "/ch/02/mix/on 0"}
    m = build(top, texts)
    anchor = m.anchors()[0]
    anchor.cells[1].unmuted = False
    # Custom-OSC cue: writes the message text to customString.
    assert m.dirty_writes() == [("m1", "customString", "/ch/01/mix/on 0")]
    assert m.mic_dirty_count() == 1


def test_x32_parameter_values_read_and_write():
    # QLab 5 X32 "network audio" cues: parameterValues lists, not text.
    top = [grp("c1", "Cue 1",
               mic("m1", 1), mic("m2", 2))]
    values = {
        "m1": ["ch", 1, "mix", "on", 0],     # ch 1 muted
        "m2": ["ch", 2, "mix", "on", 1],     # ch 2 unmuted
    }
    m = GridModel(Config(mic_count=8))
    m.build_tree(top, lambda uid: values.get(uid))
    anchor = m.anchors()[0]
    assert anchor.cells[1].unmuted is False
    assert anchor.cells[2].unmuted is True

    # Unmute channel 1 -> writes parameterValues back as JSON with value 1.
    anchor.cells[1].unmuted = True
    writes = m.dirty_writes()
    assert writes == [("m1", "parameterValues", '["ch", 1, "mix", "on", 1]')]


def test_x32_placeholder_channel_is_counted_and_skipped():
    # Channel = None ({channel} placeholder) -> no cell, but counted so the UI
    # can explain why. Value stored as a string is preserved on write.
    top = [grp("c1", "Cue 1", mic("m1", 1), mic("m2", 2))]
    values = {
        "m1": ["ch", None, "mix", "on", "0"],    # placeholder channel
        "m2": ["ch", 2, "mix", "on", "0"],       # concrete channel, string value
    }
    m = GridModel(Config(mic_count=8))
    m.build_tree(top, lambda uid: values.get(uid))
    assert m.placeholder_count == 1
    anchor = m.anchors()[0]
    assert set(anchor.cells) == {2}              # only the concrete one
    anchor.cells[2].unmuted = True
    # Value written back as a string "1" to match how it was stored.
    assert m.dirty_writes() == [("m2", "parameterValues",
                                 '["ch", 2, "mix", "on", "1"]')]


def test_set_channel_name_renames_every_cue_for_that_channel():
    # Two cues, each with channel 1 + 2 cues. Renaming channel 1 -> "Annie"
    # must rename channel-1's cue in BOTH cues (and leave channel 2 alone).
    top = [
        grp("L1", "Cue 1", mic("a1", 1), mic("a2", 2)),
        grp("L2", "Cue 2", mic("b1", 1), mic("b2", 2)),
    ]
    vals = {
        "a1": ["ch", 1, "mix", "on", 0], "a2": ["ch", 2, "mix", "on", 0],
        "b1": ["ch", 1, "mix", "on", 0], "b2": ["ch", 2, "mix", "on", 0],
    }
    m = GridModel(Config(mic_count=8))
    m.build_tree(top, lambda uid: vals.get(uid))
    changed = m.set_channel_name(1, "Annie")
    assert {n.uid for n, _ in changed} == {"a1", "b1"}
    # Both channel-1 cues are now name-dirty and queued for QLab.
    assert set(m.name_writes()) == {("a1", "name", "Annie"),
                                    ("b1", "name", "Annie")}
    assert m.name_dirty_count() == 2


def test_scribble_writes_track_name_changes():
    top = [grp("L1", "Cue 1", mic("a1", 1), mic("a2", 2))]
    vals = {"a1": ["ch", 1, "mix", "on", 0], "a2": ["ch", 2, "mix", "on", 0]}
    cfg = Config(mic_count=8)
    m = GridModel(cfg)
    m.build_tree(top, lambda uid: vals.get(uid))
    assert m.scribble_writes() == []          # nothing changed yet
    cfg.set_label(1, "Annie")
    assert m.scribble_writes() == [(1, "Annie")]
    # A full sync sends every named channel regardless of change.
    assert m.scribble_writes(only_dirty=False) == [(1, "Annie")]
    m.mark_committed()
    assert m.scribble_writes() == []          # baseline updated after submit


def test_scribble_sender_sends_osc_over_udp():
    import socket
    from qlabflash import osc
    from qlabflash.mixer import send_scribble_names

    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    srv.settimeout(2)
    port = srv.getsockname()[1]
    try:
        n = send_scribble_names("127.0.0.1", port, "/ch/{chan:02d}/config/name",
                                [(1, "Annie")])
        assert n == 1
        data, _ = srv.recvfrom(4096)
        addr, args = osc.decode_message(data)
        assert addr == "/ch/01/config/name"
        assert args == ["Annie"]
    finally:
        srv.close()


def test_scribble_sender_no_host_is_noop():
    from qlabflash.mixer import send_scribble_names
    assert send_scribble_names("", 10023, "/ch/{chan:02d}/config/name",
                               [(1, "Annie")]) == 0


def test_x32_ignores_non_onoff_parameters():
    # A fader cue (parameter 'fader') is not a mute control -> no checkbox.
    top = [grp("c1", "Cue 1", mic("m1", 1))]
    values = {"m1": ["ch", 1, "mix", "fader", 0]}
    m = GridModel(Config(mic_count=8))
    m.build_tree(top, lambda uid: values.get(uid))
    assert m.anchors() == [] or all(not a.cells for a in m.anchors())
