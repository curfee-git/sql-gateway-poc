# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""In-memory observability recorder that backs the live observability page.

Holds the last ``_MAX_BUFFERED_ENTRIES`` entries with the full rows and
columns payload, so the ``/observability`` page can render the same detail
that ``demo_output.html`` shows. This is intentional for demo purposes (see
README).

``record()`` is invoked from FastAPI's sync threadpool; subscribers live on
the event loop. We bridge the two with ``loop.call_soon_threadsafe`` so the
``asyncio.Queue`` is only mutated on its owning loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from wireup import injectable

from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto

_logger = logging.getLogger(__name__)

_MAX_BUFFERED_ENTRIES = 500
_MAX_PER_SUBSCRIBER_QUEUE_SIZE = 1_000
_SLOW_CONSUMER_WARNING_INTERVAL_SECONDS = 30.0


class _Subscriber:
    """One live SSE client. Identity-based hashing so stale entries are removable."""

    def __init__(
        self,
        queue: asyncio.Queue[ObservabilityEntryDto],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.queue = queue
        self.loop = loop
        self._drops_since_last_warning = 0
        self._last_warning_at_monotonic: float = 0.0

    def deliver(self, entry: ObservabilityEntryDto) -> None:
        if self.loop.is_closed():
            return
        # Loop may close between the is_closed() check and the call.
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self._put_if_possible, entry)

    def _put_if_possible(self, entry: ObservabilityEntryDto) -> None:
        try:
            self.queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Slow consumer: drop this entry rather than grow unbounded.
            self._drops_since_last_warning += 1
            self._maybe_warn_about_slow_consumer()

    def _maybe_warn_about_slow_consumer(self) -> None:
        now_monotonic = time.monotonic()
        if (
            now_monotonic - self._last_warning_at_monotonic
            < _SLOW_CONSUMER_WARNING_INTERVAL_SECONDS
        ):
            return
        self._last_warning_at_monotonic = now_monotonic
        dropped_in_this_window = self._drops_since_last_warning
        self._drops_since_last_warning = 0
        _logger.warning(
            "observability subscriber dropped %d entries in the last ~%.0f s "
            "(per-subscriber queue cap=%d). The SSE client is reading slower "
            "than entries are produced; consider throttling producers or "
            "raising the queue cap.",
            dropped_in_this_window,
            _SLOW_CONSUMER_WARNING_INTERVAL_SECONDS,
            _MAX_PER_SUBSCRIBER_QUEUE_SIZE,
        )


@injectable
class InMemoryObservabilityRecorderAdapter:
    """Last ``_MAX_BUFFERED_ENTRIES`` entries plus fan-out to live subscribers."""

    def __init__(self) -> None:
        self._entries: deque[ObservabilityEntryDto] = deque(
            maxlen=_MAX_BUFFERED_ENTRIES
        )
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()

    def record(self, entry: ObservabilityEntryDto) -> None:
        with self._lock:
            self._entries.append(entry)
            subscribers_snapshot = list(self._subscribers)
        for subscriber in subscribers_snapshot:
            subscriber.deliver(entry)

    def snapshot(self) -> list[ObservabilityEntryDto]:
        with self._lock:
            return list(self._entries)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[ObservabilityEntryDto]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ObservabilityEntryDto] = asyncio.Queue(
            maxsize=_MAX_PER_SUBSCRIBER_QUEUE_SIZE
        )
        subscriber = _Subscriber(queue=queue, loop=loop)
        with self._lock:
            self._subscribers.add(subscriber)
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
