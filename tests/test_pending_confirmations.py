import pytest
from hub import pending_confirmations as pc

@pytest.mark.asyncio
async def test_duplicate_create_raises_and_keeps_first_waiter():
    first = pc.create("req-dup")
    with pytest.raises(ValueError):
        pc.create("req-dup")
    assert pc.resolve("req-dup", True) is True
    assert await first is True

@pytest.mark.asyncio
async def test_create_then_resolve_sets_future_result():
    future = pc.create("req-1")
    assert pc.resolve("req-1", True) is True
    assert await future is True

@pytest.mark.asyncio
async def test_resolve_unknown_request_id_returns_false():
    assert pc.resolve("nonexistent", True) is False

@pytest.mark.asyncio
async def test_discard_removes_pending_entry():
    pc.create("req-2")
    pc.discard("req-2")
    assert pc.resolve("req-2", True) is False

@pytest.mark.asyncio
async def test_resolve_false_propagates():
    future = pc.create("req-3")
    pc.resolve("req-3", False)
    assert await future is False
