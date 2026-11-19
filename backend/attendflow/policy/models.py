"""Typed loader for policy.json and a section splitter for policy.md.

The rule engine reads every limit from here, never from hard-coded numbers.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_IDS = [f"P{i}" for i in range(1, 17)]

# Params each policy must define. Loading fails if one is missing, so the engine can
# rely on them without defensive checks.
REQUIRED_PARAMS: dict[str, set[str]] = {
    "P1": {"open_shift_grace_hours"},
    "P2": {"duplicate_window_minutes"},
    "P3": {"max_hours_per_day"},
    "P4": {"break_required_after_hours", "min_break_minutes"},
    "P5": {"weekly_overtime_after_hours", "planned_break_after_hours", "planned_break_minutes"},
    "P6": {"min_rest_hours"},
    "P7": {"grace_minutes"},
    "P12": {"max_sick_days_without_certificate"},
    "P13": {"half_day_hours"},
    "P14": {"compensation_options"},
    "P15": {
        "attribute_to",
        "match_before_start_hours",
        "match_after_end_hours",
        "max_shift_hours",
    },
    "P16": {"max_consecutive_days"},
}

ParamValue = int | float | bool | str | list[str]


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: Literal["info", "low", "medium", "high"]
    auto_resolve: bool = False
    params: dict[str, ParamValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _numbers_positive(self) -> PolicyRule:
        for name, value in self.params.items():
            if isinstance(value, int | float) and not isinstance(value, bool) and value <= 0:
                raise ValueError(f"param {name} must be > 0, got {value}")
        return self


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    effective_from: date
    week_starts_on: Literal["monday"]
    policies: dict[str, PolicyRule]

    @model_validator(mode="after")
    def _all_policies_present(self) -> PolicyConfig:
        ids = set(self.policies)
        missing = [p for p in POLICY_IDS if p not in ids]
        unknown = sorted(ids - set(POLICY_IDS))
        if missing or unknown:
            raise ValueError(f"policy ids missing={missing} unknown={unknown}")
        for pid, required in REQUIRED_PARAMS.items():
            absent = required - self.policies[pid].params.keys()
            if absent:
                raise ValueError(f"{pid} is missing param(s) {sorted(absent)}")
        return self

    def param(self, policy_id: str, name: str) -> ParamValue:
        return self.policies[policy_id].params[name]

    def number(self, policy_id: str, name: str) -> float:
        """A numeric limit as a float. Fails loudly if the param is not a number."""
        value = self.param(policy_id, name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError(f"{policy_id}.{name} is not a number: {value!r}")
        return float(value)


def load_policy(path: Path) -> PolicyConfig:
    return PolicyConfig.model_validate_json(path.read_text(encoding="utf-8"))


_SECTION_RE = re.compile(r"^## (P\d+):", re.MULTILINE)


def load_policy_text(path: Path) -> dict[str, str]:
    """Split policy.md into {policy_id: section text}. Sections start with '## P<n>: '."""
    text = path.read_text(encoding="utf-8")
    matches = list(_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[m.start() : end].strip()
    return sections
