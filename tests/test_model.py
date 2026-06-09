from qlabflash.config import Config
from qlabflash.model import Cue, GridModel


def make_model():
    return GridModel(Config(mic_count=32))


def test_channel_labels_set_clear_and_persist(tmp_path):
    cfg = Config(mic_count=32)
    assert cfg.header_text(1) == "1"
    cfg.set_label(1, "Doug")
    cfg.set_label(2, "  Steve  ")
    assert cfg.label_for(1) == "Doug"
    assert cfg.label_for(2) == "Steve"      # trimmed
    assert cfg.header_text(1) == "Doug"
    assert cfg.has_labels()

    path = tmp_path / "cfg.json"
    cfg.save(str(path))
    reloaded = Config.load(str(path))
    assert reloaded.label_for(1) == "Doug"

    cfg.set_label(1, "")                      # blank clears
    assert cfg.label_for(1) == ""
    assert "1" not in cfg.channel_labels


def test_parse_channel_on_off():
    m = make_model()
    assert m.parse_channel("/ch/01/mix/on 1") == (1, True)
    assert m.parse_channel("/ch/32/mix/on 0") == (32, False)
    assert m.parse_channel("/ch/3/mix/on 1") == (3, True)


def test_parse_channel_rejects_non_mic_and_out_of_range():
    m = make_model()
    assert m.parse_channel("/go") is None
    assert m.parse_channel("/ch/40/mix/on 1") is None  # beyond mic_count
    assert m.parse_channel("") is None


def test_candidate_uids_returns_all_leaves():
    cue = Cue(uid="g1", number="1", name="L1", type="Group", children=[
        Cue(uid="n1", number="", name="", type="Network"),
        Cue(uid="sub", number="", name="", type="Group", children=[
            Cue(uid="n2", number="", name="", type="Network"),
        ]),
    ])
    assert set(make_model().candidate_uids([cue])) == {"n1", "n2"}
