"""End-to-end test against the mock QLab server over real UDP sockets."""

import time

import pytest

from qlabflash.config import Config
from qlabflash.mock_qlab import MockQLab, WORKSPACE_ID
from qlabflash.qlab import QLabClient
from qlabflash.session import WorkspaceSession


@pytest.fixture
def mock_and_client():
    # Port 0 lets the OS pick a free port for the mock; client points at it.
    mock = MockQLab(host="127.0.0.1", port=0, num_looks=4, mic_count=32)
    client = QLabClient(host="127.0.0.1", send_port=mock.port, listen_port=0,
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
    assert len(model.rows) == 4               # 4 looks
    # Every row should have all 32 mic cells backed by real cues.
    for row in model.rows:
        assert len(row.cells) == 32

    # Flip channel 5 in look 1 and submit.
    target = model.rows[0].cells[5]
    new_state = not target.unmuted
    target.unmuted = new_state
    written = session.submit(only_dirty=True)
    assert written == 1

    # Give the mock a moment to apply the set, then re-read and confirm.
    time.sleep(0.1)
    session2 = WorkspaceSession(client, WORKSPACE_ID, config)
    model2 = session2.load_grid()
    assert model2.rows[0].cells[5].unmuted == new_state


def test_submit_all(mock_and_client):
    mock, client = mock_and_client
    config = Config(mic_count=32)
    session = WorkspaceSession(client, WORKSPACE_ID, config)
    session.load_grid()
    written = session.submit(only_dirty=False)
    assert written == 4 * 32
