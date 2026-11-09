# tests/test_devices.py
import pytest
from hub import devices

@pytest.fixture(autouse=True)
def _reset():
    devices.reset_for_tests()
    yield
    devices.reset_for_tests()

def test_register_hub_self_is_always_connected():
    device_id = devices.register_hub_self()
    assert devices.is_hub_device(device_id) is True
    assert devices.is_connected(device_id) is True

def test_register_chat_then_lookup_by_ws():
    ws = object()
    devices.register_chat("laptop-host", "laptop", ws)
    assert devices.get_device_id_for_chat_ws(ws) == "laptop-host"

def test_unregister_chat_clears_lookup():
    ws = object()
    devices.register_chat("laptop-host", "laptop", ws)
    devices.unregister_chat(ws)
    assert devices.get_device_id_for_chat_ws(ws) is None

def test_register_agent_then_get_agent_ws():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    assert devices.get_agent_ws("laptop-host") is ws

def test_unregister_agent_clears_ws():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    devices.unregister_agent(ws)
    assert devices.get_agent_ws("laptop-host") is None

def test_chat_only_device_is_connected_but_cannot_execute():
    devices.register_chat("laptop-host", "laptop", object())
    assert devices.is_connected("laptop-host") is True
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries["laptop-host"]["can_execute"] is False

def test_agent_device_can_execute():
    devices.register_agent("laptop-host", "laptop", object())
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries["laptop-host"]["can_execute"] is True

def test_unknown_device_is_not_connected():
    assert devices.is_connected("nonexistent-host") is False

def test_chat_and_agent_same_device_share_one_entry():
    devices.register_agent("laptop-host", "laptop", object())
    devices.register_chat("laptop-host", "laptop", object())
    assert len(devices.list_connected()) == 1

def test_reregistering_same_ws_does_not_duplicate():
    ws = object()
    devices.register_agent("laptop-host", "laptop", ws)
    devices.register_agent("laptop-host", "laptop", ws)
    assert len(devices.list_connected()) == 1

def test_different_ws_same_device_last_registration_wins():
    first, second = object(), object()
    devices.register_agent("laptop-host", "laptop", first)
    devices.register_agent("laptop-host", "laptop", second)
    assert devices.get_agent_ws("laptop-host") is second
    assert len(devices.list_connected()) == 1

    devices.register_chat("laptop-host", "laptop", first)
    devices.register_chat("laptop-host", "laptop", second)
    assert devices.get_device_id_for_chat_ws(first) is None
    assert devices.get_device_id_for_chat_ws(second) == "laptop-host"

def test_local_chat_on_hub_machine_is_recognized_as_hub():
    # A client run on the hub machine reports the hub's hostname; it must be
    # recognized so commands default to running on the hub.
    hub_id = devices.register_hub_self()
    ws = object()
    devices.register_chat(hub_id, "hub", ws, is_local=True)
    assert devices.get_device_id_for_chat_ws(ws) == hub_id
    assert devices.is_hub_device(hub_id) is True
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert len(entries) == 1
    assert entries[hub_id]["can_execute"] is True

    devices.unregister_chat(ws)
    assert devices.get_device_id_for_chat_ws(ws) is None
    assert devices.is_connected(hub_id) is True  # the hub itself stays live

def test_remote_chat_cannot_claim_hub_device_id():
    hub_id = devices.register_hub_self()
    omitted, explicit = object(), object()
    devices.register_chat(hub_id, "hub", omitted)
    devices.register_chat(hub_id, "hub", explicit, is_local=False)
    assert devices.get_device_id_for_chat_ws(omitted) is None
    assert devices.get_device_id_for_chat_ws(explicit) is None

def test_agent_cannot_claim_hub_device_id():
    hub_id = devices.register_hub_self()
    ws = object()
    devices.register_agent(hub_id, "hub", ws)
    assert devices.get_agent_ws(hub_id) is None
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert list(entries) == [hub_id]  # still just the hub itself, no agent attached

def test_chat_reregistering_under_new_id_detaches_old_entry():
    ws = object()
    devices.register_chat("old-host", "old", ws)
    devices.register_chat("new-host", "new", ws)
    assert devices.get_device_id_for_chat_ws(ws) == "new-host"
    ids = {d["device_id"] for d in devices.list_connected()}
    assert ids == {"new-host"}

def test_agent_reregistering_under_new_id_detaches_old_entry():
    ws = object()
    devices.register_agent("old-host", "old", ws)
    devices.register_agent("new-host", "new", ws)
    assert devices.get_agent_ws("old-host") is None
    assert devices.get_agent_ws("new-host") is ws
    ids = {d["device_id"] for d in devices.list_connected()}
    assert ids == {"new-host"}

def test_empty_device_id_is_rejected():
    ws = object()
    devices.register_chat("", "laptop", ws)
    devices.register_agent("", "laptop", ws)
    devices.register_chat(None, "laptop", ws)  # type: ignore[arg-type]
    devices.register_agent(None, "laptop", ws)  # type: ignore[arg-type]
    assert devices.get_device_id_for_chat_ws(ws) is None
    assert devices.get_agent_ws("") is None
    assert devices.list_connected() == []


@pytest.mark.parametrize(
    "bad_id",
    [
        'bad"id',
        "bad\\id",
        "bad\nid",
        '"); DROP TABLE',
        "x" * 65,
        "bad/id",
        "bad\x00id",
    ],
)
def test_unsafe_device_id_is_rejected(bad_id):
    chat_ws, agent_ws = object(), object()
    devices.register_chat(bad_id, "laptop", chat_ws)
    devices.register_agent(bad_id, "laptop", agent_ws)
    assert devices.get_device_id_for_chat_ws(chat_ws) is None
    assert devices.get_agent_ws(bad_id) is None
    assert devices.list_connected() == []


@pytest.mark.parametrize(
    "bad_name",
    [
        'bad"name',
        "bad\\name",
        "bad\nname",
        '"); DROP TABLE',
        "x" * 65,
        "bad:name",
        "bad\x00name",
    ],
)
def test_unsafe_device_name_rejects_whole_registration(bad_name):
    # A valid device_id paired with an unsafe name must not register at all:
    # no sanitized/truncated name, no partial entry.
    chat_ws, agent_ws = object(), object()
    devices.register_chat("laptop-host", bad_name, chat_ws)
    devices.register_agent("laptop-host", bad_name, agent_ws)
    assert devices.get_device_id_for_chat_ws(chat_ws) is None
    assert devices.get_agent_ws("laptop-host") is None
    assert devices.list_connected() == []


def test_safe_charset_device_id_and_name_are_accepted():
    ws = object()
    devices.register_agent("My Laptop_1.local-2", "Desk PC.v2_x", ws)
    assert devices.get_agent_ws("My Laptop_1.local-2") is ws
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries["My Laptop_1.local-2"]["device_name"] == "Desk PC.v2_x"


def test_boundary_length_64_is_accepted_and_65_rejected():
    ok_id = "a" * 64
    devices.register_agent(ok_id, None, object())
    assert devices.is_connected(ok_id) is True
    devices.register_agent("b" * 65, None, object())
    assert devices.is_connected("b" * 65) is False
