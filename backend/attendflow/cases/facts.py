"""A stable fingerprint of the engine facts behind one exception.

Detection refreshes these fields on an open case. An investigation stores the hash of
what it saw, so the scheduler can tell "already investigated" from "the facts changed
since" without calling the LLM again for nothing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Fields detection refreshes on an open exception.
CONTENT_FIELDS = ("title", "summary", "severity", "kind", "details", "evidence", "fix_options")


def facts_hash(row: Any) -> str:
    facts = {name: getattr(row, name) for name in CONTENT_FIELDS}
    blob = json.dumps(facts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
