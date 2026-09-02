"""In-memory per-run event fan-out for the WS progress endpoint.

Single-process, no external broker — deliberately minimal for this phase.
Revisit if the pipeline ever needs to run across multiple worker processes."""

import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


def subscribe(run_id: int) -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _subscribers[run_id].append(queue)
    return queue


def unsubscribe(run_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
    _subscribers[run_id].remove(queue)
    if not _subscribers[run_id]:
        del _subscribers[run_id]


def publish(run_id: int, event: dict[str, Any]) -> None:
    for queue in _subscribers.get(run_id, []):
        queue.put_nowait(event)
