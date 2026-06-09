from qlabflash.config import Config
from qlabflash.model import Cue, GridModel


def make_model():
    return GridModel(Config(mic_count=32))


def test_parse_channel_on_off():
    m = make_model()
    assert m.parse_channel("/ch/01/mix/on 1") == (1, True)
    assert m.parse_channel("/ch/32/mix/on 0") == (32, False)
    # Leading-zero-insensitive channel parsing.
    assert m.parse_channel("/ch/3/mix/on 1") == (3, True)


def test_parse_channel_rejects_non_mic_and_out_of_range():
    m = make_model()
    assert m.parse_channel("/go") is None
    assert m.parse_channel("/ch/40/mix/on 1") is None  # beyond mic_count
    assert m.parse_channel("") is None


def test_build_grid_from_group():
    m = make_model()
    cues = [
        Cue(uid="g1", number="1", name="Look 1", type="Group", children=[
            Cue(uid="n1", number="1.1", name="Ch1", type="Network"),
            Cue(uid="n3", number="1.3", name="Ch3", type="Network"),
        ])
    ]
    texts = {"n1": "/ch/01/mix/on 1", "n3": "/ch/03/mix/on 0"}
    rows = m.build(cues, lambda uid: texts.get(uid))
    assert len(rows) == 1
    row = rows[0]
    assert row.label == "1 Look 1"
    assert row.cells[1].unmuted is True
    assert row.cells[1].cue_uid == "n1"
    assert row.cells[3].unmuted is False
    assert 2 not in row.cells  # no backing cue for channel 2


def test_dirty_writes_only_changed():
    m = make_model()
    cues = [Cue(uid="g1", number="1", name="L1", type="Group", children=[
        Cue(uid="n1", number="1.1", name="Ch1", type="Network"),
        Cue(uid="n2", number="1.2", name="Ch2", type="Network"),
    ])]
    texts = {"n1": "/ch/01/mix/on 1", "n2": "/ch/02/mix/on 0"}
    rows = m.build(cues, lambda uid: texts.get(uid))
    # Flip channel 1 from unmuted to muted.
    rows[0].cells[1].unmuted = False
    writes = m.dirty_writes()
    assert writes == [("n1", "/ch/01/mix/on 0")]
    # All-writes includes both.
    assert set(m.all_writes()) == {
        ("n1", "/ch/01/mix/on 0"),
        ("n2", "/ch/02/mix/on 0"),
    }


def test_mark_committed_resets_dirty():
    m = make_model()
    cues = [Cue(uid="g1", number="1", name="L1", type="Group", children=[
        Cue(uid="n1", number="1.1", name="Ch1", type="Network"),
    ])]
    m.build(cues, lambda uid: "/ch/01/mix/on 1")
    m.rows[0].cells[1].unmuted = False
    assert m.dirty_writes()
    m.mark_committed()
    assert m.dirty_writes() == []


def test_nested_mics_group_and_empty_row_filtering():
    m = make_model()
    cues = [
        # A real cue: group -> Mics group (32) + non-mic siblings.
        Cue(uid="cue1", number="1", name="Cue 1", type="Group", children=[
            Cue(uid="mics1", number="", name="Mics", type="Group", children=[
                Cue(uid="n1", number="", name="Ch1", type="Network"),
                Cue(uid="n2", number="", name="Ch2", type="Network"),
            ]),
            Cue(uid="lx1", number="", name="Lights", type="Network"),
        ]),
        # A standalone cue sprinkled between — no mics.
        Cue(uid="note1", number="", name="Note", type="Memo"),
    ]
    texts = {
        "n1": "/ch/01/mix/on 1",
        "n2": "/ch/02/mix/on 0",
        "lx1": "/eos/chan/1/out 100",  # non-mic, must be ignored
    }
    rows = m.build(cues, lambda uid: texts.get(uid))
    # The standalone Note cue is dropped; only the real cue remains.
    assert len(rows) == 1
    assert rows[0].label == "1 Cue 1"
    assert set(rows[0].cells) == {1, 2}  # mics found despite nesting

    # show_empty keeps the empty standalone cue as a row.
    rows = m.build(cues, lambda uid: texts.get(uid), show_empty=True)
    assert len(rows) == 2


def test_mics_group_name_filter_restricts_search():
    m = make_model()
    cues = [Cue(uid="cue1", number="1", name="Cue 1", type="Group", children=[
        Cue(uid="mics1", number="", name="Mics", type="Group", children=[
            Cue(uid="n1", number="", name="Ch1", type="Network"),
        ]),
        # A stray mic-looking message OUTSIDE the Mics group.
        Cue(uid="stray", number="", name="FX", type="Network"),
    ])]
    texts = {"n1": "/ch/01/mix/on 1", "stray": "/ch/05/mix/on 1"}

    # No filter: both are picked up.
    rows = m.build(cues, lambda uid: texts.get(uid))
    assert set(rows[0].cells) == {1, 5}
    # With filter: only the one inside the "Mics" group.
    rows = m.build(cues, lambda uid: texts.get(uid), mics_group_name="Mics")
    assert set(rows[0].cells) == {1}
    # candidate_uids honours the filter too.
    assert m.candidate_uids(cues, mics_group_name="Mics") == ["n1"]


def test_leaf_uids_skips_containers():
    cue = Cue(uid="g1", number="1", name="L1", type="Group", children=[
        Cue(uid="n1", number="", name="", type="Network"),
        Cue(uid="sub", number="", name="", type="Group", children=[
            Cue(uid="n2", number="", name="", type="Network"),
        ]),
    ])
    assert set(cue.leaf_uids()) == {"n1", "n2"}
