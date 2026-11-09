"""Registry of pending destructive-action confirmations.

A coroutine calls ``create(request_id)`` and awaits the returned future. A
separate message handler calls ``resolve(request_id, approved)`` when the
client replies. If the wait times out, the waiter calls ``discard`` so a late
reply cannot resolve a future nobody awaits anymore.
"""

import asyncio

_pending: dict[str, asyncio.Future] = {}


def create(request_id: str) -> asyncio.Future:
    """Create and register a future for ``request_id``. Must run inside an event loop.

    Raises ValueError if ``request_id`` is already pending, so an existing
    waiter is never silently orphaned.
    """
    if request_id in _pending:
        raise ValueError(f"request_id {request_id!r} already pending")
    future = asyncio.get_running_loop().create_future()
    _pending[request_id] = future
    return future


def resolve(request_id: str, approved: bool) -> bool:
    """Resolve the pending future for ``request_id``.

    Returns False if the id is unknown (already resolved, discarded, or never
    created); True otherwise.
    """
    future = _pending.pop(request_id, None)
    if future is None:
        return False
    if not future.done():
        future.set_result(approved)
    return True


def discard(request_id: str) -> None:
    """Forget ``request_id`` without resolving its future."""
    _pending.pop(request_id, None)
