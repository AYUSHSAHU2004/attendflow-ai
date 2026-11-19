"""The one place "now" comes from.

The demo runs at a fixed moment (ATTENDFLOW_AS_OF, Thu 16 Apr 2026 08:00), so every
created_at, updated_at and waiting_since uses it, never the server clock. Rows are ordered
by their sequential id, not by time. The Phase 11 scheduler keeps this fixed clock (a
simulated punch carries its own explicit timestamp); its own run times are real UTC
because they describe the server. Another clock only has to implement now().
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class FixedClock:
    def __init__(self, at: datetime):
        if at.tzinfo is not None:
            raise ValueError("the clock must use plain local time (no timezone)")
        self._at = at

    def now(self) -> datetime:
        return self._at
