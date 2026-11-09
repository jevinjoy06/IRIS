# tests/test_brain.py
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hub import brain, devices


@pytest.fixture(autouse=True)
def _reset_devices():
    devices.reset_for_tests()
    yield
    devices.reset_for_tests()


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, finish_reason=None, content=None, tool_calls=None):
        self.finish_reason = finish_reason
        self.delta = _FakeDelta(content=content, tool_calls=tool_calls)


class _FakeChunk:
    def __init__(self, choice):
        self.choices = [choice]


def _fake_client():
    """A fake Ollama/OpenAI-compatible client good enough to let process_turn's
    main loop finish a single, no-tool-call turn without touching the network.

    Streaming calls (stream=True) yield one chunk with finish_reason="stop" and
    no tool calls, so the while-loop in process_turn breaks immediately after
    the deterministic pre-seed path (if any) has already run. Non-streaming
    calls (used by the background fact-extraction/labeling tasks) get a stub
    response shaped like what those call sites expect.
    """
    async def create(**kwargs):
        if kwargs.get("stream"):
            async def gen():
                yield _FakeChunk(_FakeChoice(finish_reason="stop", content="ok"))
            return gen()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_process_turn_passes_origin_device_id_to_async_dispatch(monkeypatch, temp_db):
    devices.register_agent("laptop-host", "laptop", AsyncMock())
    captured = {}

    async def fake_async_dispatch(tool_name, tool_input, ws, origin_device_id=None):
        captured["origin_device_id"] = origin_device_id
        return '{"ok": true}'

    monkeypatch.setattr(brain, "async_dispatch", fake_async_dispatch)
    monkeypatch.setattr(brain, "_get_client", _fake_client)

    ws = AsyncMock()
    # "clipboard" with no "copy" forces the clipboard_read deterministic
    # pre-seed path (lines ~190-217), which is the cheapest way to exercise
    # async_dispatch without a fully mocked streaming tool-call round trip.
    await brain.process_turn(
        "what's on my clipboard", ws, session_id=None, turn_number=1,
        origin_device_id="laptop-host",
    )

    assert captured["origin_device_id"] == "laptop-host"


@pytest.mark.asyncio
async def test_system_prompt_lists_connected_devices(monkeypatch, temp_db):
    devices.register_hub_self()
    devices.register_agent("laptop-host", "laptop", AsyncMock())

    from hub.brain import _device_context
    ctx = _device_context()
    assert "laptop-host" in ctx
