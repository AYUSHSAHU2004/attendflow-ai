import json

import pytest
from pydantic import ValidationError

from attendflow.policy import load_policy, load_policy_text
from attendflow.policy.models import POLICY_IDS, PolicyConfig
from attendflow.scripts.validate_data import validate_policy_files
from tests.conftest import DATA_DIR, replace_in_file

EXPECTED_LIMITS = {
    ("P2", "duplicate_window_minutes"): 5,
    ("P3", "max_hours_per_day"): 9,
    ("P4", "break_required_after_hours"): 5,
    ("P4", "min_break_minutes"): 30,
    ("P5", "weekly_overtime_after_hours"): 40,
    ("P6", "min_rest_hours"): 11,
    ("P7", "grace_minutes"): 10,
    ("P12", "max_sick_days_without_certificate"): 2,
    ("P13", "half_day_hours"): 4,
    ("P16", "max_consecutive_days"): 6,
}


@pytest.fixture(scope="module")
def raw_policy() -> dict:
    return json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))


def test_policy_has_all_ids_and_agreed_limits():
    policy = load_policy(DATA_DIR / "policy.json")
    assert list(policy.policies) == POLICY_IDS
    for (pid, name), value in EXPECTED_LIMITS.items():
        assert policy.param(pid, name) == value, (pid, name)


def test_only_low_risk_types_auto_resolve():
    policy = load_policy(DATA_DIR / "policy.json")
    assert {pid for pid, r in policy.policies.items() if r.auto_resolve} == {"P2", "P7"}


def test_missing_policy_id_fails(raw_policy):
    broken = json.loads(json.dumps(raw_policy))
    del broken["policies"]["P9"]
    with pytest.raises(ValidationError, match="P9"):
        PolicyConfig.model_validate(broken)


def test_missing_required_param_fails(raw_policy):
    broken = json.loads(json.dumps(raw_policy))
    broken["policies"]["P3"]["params"] = {}
    with pytest.raises(ValidationError, match="max_hours_per_day"):
        PolicyConfig.model_validate(broken)


def test_non_positive_limit_fails(raw_policy):
    broken = json.loads(json.dumps(raw_policy))
    broken["policies"]["P7"]["params"]["grace_minutes"] = -5
    with pytest.raises(ValidationError, match="grace_minutes"):
        PolicyConfig.model_validate(broken)


def test_policy_md_has_a_section_per_id():
    sections = load_policy_text(DATA_DIR / "policy.md")
    assert sorted(sections, key=lambda p: int(p[1:])) == POLICY_IDS
    assert sections["P2"].startswith("## P2: Duplicate punches")


def test_policy_files_in_sync():
    assert validate_policy_files(DATA_DIR) == []


def test_policy_text_out_of_sync_is_caught(data_copy):
    replace_in_file(data_copy / "policy.json", '"grace_minutes": 10', '"grace_minutes": 15')
    assert validate_policy_files(data_copy) == ["policy.md P7: does not mention grace_minutes=15"]
