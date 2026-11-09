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

def test_external_chat_cannot_claim_hub_device_id():
    hub_id = devices.register_hub_self()
    ws = object()
    devices.register_chat(hub_id, "hub", ws)
    assert devices.get_device_id_for_chat_ws(ws) is None
    assert devices.get_agent_ws(hub_id) is None

def test_external_agent_cannot_claim_hub_device_id():
    hub_id = devices.register_hub_self()
    ws = object()
    devices.register_agent(hub_id, "hub", ws)
    assert devices.get_agent_ws(hub_id) is None
    entries = {d["device_id"]: d for d in devices.list_connected()}
    assert entries[hub_id]["can_execute"] is True  # still just the hub itself

def test_hub_registration_evicts_earlier_external_claim_on_same_hostname():
    import socket
    hostname = socket.gethostname()
    ws = object()
    devices.register_chat(hostname, "laptop", ws)
    devices.register_hub_self()
    assert devices.get_device_id_for_chat_ws(ws) is None
    assert devices.is_hub_device(hostname) is True

def test_empty_device_id_is_rejected():
    ws = object()
    devices.register_chat("", "laptop", ws)
    devices.register_agent("", "laptop", ws)
    devices.register_chat(None, "laptop", ws)  # type: ignore[arg-type]
    devices.register_agent(None, "laptop", ws)  # type: ignore[arg-type]
    assert devices.get_device_id_for_chat_ws(ws) is None
    assert devices.get_agent_ws("") is None
    assert devices.list_connected() == []
