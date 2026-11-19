"""The one place "now" comes from.

The demo runs at a fixed moment (ATTENDFLOW_AS_OF, Thu 16 Apr 2026 08:00), so every
created_at, updated_at and waiting_since uses it, never the server clock. Rows are ordered
by their sequential id, not by time. The Phase 11 scheduler keeps this fixed clock (a
simulated punch carries its own explicit timestamp); its own run times are real UTC
because they describe the server. Another clock only has to implement now().

Phase 13 splits "now" in two:
- `now()` is the time stamped on rows and used by the no-reply ladder. In demo mode the
  payroll admin can move it forward (DemoClock) to show the ladder in a video.
- `data_as_of()` is the cut-off for the data: detection, fixes, the worker time checks
  and device punches. It never moves, so moving the demo clock never turns Thursday's
  shifts (no punches after the as-of) into new missed-punch cases.
Use `data_as_of(clock)` for the data cut-off; it falls back to now() for simple clocks.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Protocol

# The demo clock can move at most this far ahead of the as-of time.
MAX_DEMO_OFFSET = timedelta(days=14)


class Clock(Protocol):
    def now(self) -> datetime: ...


def data_as_of(clock: Clock) -> datetime:
    """The data cut-off: punches after it do not exist yet, schedule after it is forecast."""
    fn = getattr(clock, "data_as_of", None)
    return fn() if fn is not None else clock.now()


class FixedClock:
    def __init__(self, at: datetime):
        if at.tzinfo is not None:
            raise ValueError("the clock must use plain local time (no timezone)")
        self._at = at

    def now(self) -> datetime:
        return self._at

    def data_as_of(self) -> datetime:
        return self._at


class DemoClock:
    """The as-of time plus an offset that only moves forward (demo mode only).

    The offset is kept in memory for speed and stored in the `settings` table by the
    demo endpoint, so it survives an API restart (loaded at startup). A demo reset sets it
    back to zero. With demo mode off the offset is never loaded or moved: the clock stays
    fixed at the as-of time and no timeout ever fires (Phase 22 checklist)."""

    def __init__(self, at: datetime, offset: timedelta = timedelta(0)):
        if at.tzinfo is not None:
            raise ValueError("the clock must use plain local time (no timezone)")
        self._at = at
        self._lock = threading.Lock()
        self._offset = timedelta(0)
        self.set_offset(offset)

    @property
    def offset(self) -> timedelta:
        return self._offset

    def set_offset(self, offset: timedelta) -> None:
        if offset < timedelta(0) or offset > MAX_DEMO_OFFSET:
            raise ValueError(f"the demo clock offset must be between 0 and {MAX_DEMO_OFFSET}")
        with self._lock:
            self._offset = offset

    def now(self) -> datetime:
        return self._at + self._offset

    def data_as_of(self) -> datetime:
        return self._at
