"""End-to-end test against the mock QLab server over real UDP sockets."""

import time

import pytest

from qlabflash.config import Config
from qlabflash.mock_qlab import MockQLab, WORKSPACE_ID
from qlabflash.qlab import QLabClient
from qlabflash.session import WorkspaceSession


@pytest.fixture(params=["tcp", "udp"])
def mock_and_client(request):
    # Exercise both transports. Port 0 lets the OS pick a free port.
    transport = request.param
    mock = MockQLab(host="127.0.0.1", port=0, transport=transport,
                    num_cues=4, mic_count=32)
    client = QLabClient(host="127.0.0.1", port=mock.port, transport=transport,
                        reply_timeout=3.0)
    try:
        yield mock, client
    finally:
        client.close()
        mock.close()


def test_discover_and_connect(mock_and_client):
    mock, client = mock_and_client
    workspaces = client.workspaces()
    assert len(workspaces) == 1
    assert workspaces[0]["uniqueID"] == WORKSPACE_ID
    status = client.connect_workspace(WORKSPACE_ID)
    assert status == "ok"


def test_load_grid_and_submit(mock_and_client):
    mock, client = mock_and_client
    config = Config(mic_count=32)
    session = WorkspaceSession(client, WORKSPACE_ID, config)

    model = session.load_grid()
    anchors = model.anchors()
    assert len(anchors) == 4                  # 4 cue groups carry mic checkboxes
    # Each carries all 32 mic cells, even though mics are nested in a "Mics"
    # group alongside audio/lights siblings.
    for a in anchors:
        assert len(a.cells) == 32

    # Flip channel 5 in the first cue and submit.
    target = anchors[0].cells[5]
    new_state = not target.unmuted
    target.unmuted = new_state
    mics, names, scribble = session.submit(only_dirty=True)
    assert (mics, names) == (1, 0)

    # Give the mock a moment to apply the set, then re-read and confirm.
    time.sleep(0.1)
    session2 = WorkspaceSession(client, WORKSPACE_ID, config)
    model2 = session2.load_grid()
    assert model2.anchors()[0].cells[5].unmuted == new_state


def test_submit_all(mock_and_client):
    mock, client = mock_and_client
    config = Config(mic_count=32)
    session = WorkspaceSession(client, WORKSPACE_ID, config)
    session.load_grid()
    mics, names, scribble = session.submit(only_dirty=False)
    assert mics == 4 * 32 and names == 0


def test_large_show_over_tcp():
    # A realistically large show: the /cueLists reply is far bigger than a UDP
    # datagram could hold. TCP + SLIP must stream it whole.
    mock = MockQLab(host="127.0.0.1", port=0, transport="tcp",
                    num_cues=60, mic_count=32)
    client = QLabClient(host="127.0.0.1", port=mock.port, transport="tcp",
                        reply_timeout=5.0)
    try:
        session = WorkspaceSession(client, WORKSPACE_ID, Config(mic_count=32))
        model = session.load_grid()
        anchors = model.anchors()
        assert len(anchors) == 60
        assert all(len(a.cells) == 32 for a in anchors)
    finally:
        client.close()
        mock.close()


def test_rename_cues_over_tcp():
    mock = MockQLab(host="127.0.0.1", port=0, transport="tcp",
                    num_cues=3, mic_count=8)
    client = QLabClient(host="127.0.0.1", port=mock.port, transport="tcp",
                        reply_timeout=5.0)
    try:
        session = WorkspaceSession(client, WORKSPACE_ID, Config(mic_count=8))
        session.fetch_cue_lists()
        # Rename the first cue group and one mic cue.
        n = session.rename_cues([("group-1", "Top of Act 1"),
                                 ("net-1-1", "Doug")])
        assert n == 2
        time.sleep(0.1)
        cue_lists = session.fetch_cue_lists()  # re-read
        main = cue_lists[0]
        assert main.children[0].name == "Top of Act 1"
    finally:
        client.close()
        mock.close()
