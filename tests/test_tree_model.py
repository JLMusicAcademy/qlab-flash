"""Tests for the dynamic look-anchor detection at arbitrary nesting depths."""

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


def test_act_spanning_two_cues_splits_into_two_looks():
    # Act 1 contains Cue 1 and Cue 2, each with its own Ch1/Ch2. The Act has
    # duplicate channels, so it must NOT be a look; the two cues become looks.
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
    assert m.name_writes() == [("c1", "Top of Act 1")]
    assert m.name_dirty_count() == 1
    m.mark_committed()
    assert m.name_dirty_count() == 0


def test_mic_writes_only_dirty():
    top = [grp("c1", "Cue 1", mic("m1", 1), mic("m2", 2))]
    texts = {"m1": "/ch/01/mix/on 1", "m2": "/ch/02/mix/on 0"}
    m = build(top, texts)
    anchor = m.anchors()[0]
    anchor.cells[1].unmuted = False
    assert m.dirty_writes() == [("m1", "/ch/01/mix/on 0")]
    assert m.mic_dirty_count() == 1
