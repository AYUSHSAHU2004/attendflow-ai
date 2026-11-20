"""Phase 18: runtime settings. Priya (payroll admin) can change a small whitelist of
operational settings while the app runs. No restart, no LLM, no source-data writes.

Effective value = an override stored in the `settings` table (one row, key
`runtime_overrides`, value `{key: value}`), else the value the server started with (from
the environment / .env), else the code default. Everything else stays locked:
policy.json rules and limits, LLM key/URL/model, demo mode and clock, passwords, the
database URL, the as-of time and the diagnostics flag.

Rules:
- Only the payroll admin may change or reset a setting, with a reason of 10+ characters.
  Turning auto-resolve ON needs an explicit `confirm`. In the deployed Locked profile
  (deployed, demo mode off) changes are refused; reading still works.
- Every change and reset writes one audit row (`settings_changed` / `settings_reset`,
  actor admin) with the key, old and new value and source, and the reason. Locked keys,
  secrets and anything else never appear in these rows.
- Changes never act retroactively: the scheduler reads the values once at the start of a
  cycle, ladder limits are stored on each case when its wait starts (migration 0011), and
  auto-resolve only ever touches newly detected cases.
- This module writes only the `settings` row and audit rows (a static test checks it).

Reading is a single primary-key lookup per request or scheduler cycle. There is no cache,
so there is no stale value and no shared state between the API threads and the scheduler
thread: every reader builds its own frozen `Settings`. Writers lock the overrides row
(`SELECT ... FOR UPDATE`), so two changes can never overwrite each other.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, fields, replace
from math import isfinite
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from attendflow.cases.admin import require_admin
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.models import AuditLogRow, EmployeeRow, SettingRow
from attendflow.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from attendflow.policy.models import PolicyConfig

log = logging.getLogger("attendflow.settings")

OVERRIDES_KEY = "runtime_overrides"
MIN_REASON = 10
HISTORY_ACTIONS = ("settings_changed", "settings_reset")
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200

Kind = Literal["bool", "int", "half"]  # half = a number in steps of 0.5
Source = Literal["default", "env", "override"]


class InvalidSettingError(AppError):
    status_code = 422
    code = "invalid_setting_value"


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    kind: Kind
    group: str
    help: str
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None  # "h", "s" or None

    @property
    def env(self) -> str:
        return self.key.upper()


S = Spec
EDITABLE: tuple[Spec, ...] = (
    S(
        "auto_resolve_enabled",
        "Auto-resolve low-risk exceptions",
        "bool",
        "Auto-resolve",
        "P2 duplicate taps and P7 late arrivals within grace close without a person. "
        "Turning it on needs confirm; it never touches cases already detected.",
    ),
    S(
        "no_reply_reminder_hours",
        "No-reply reminder after",
        "int",
        "No-reply ladder",
        "Hours of silence before the worker gets one reminder. Applies to new waits only.",
        1,
        72,
        "h",
    ),
    S(
        "no_reply_supervisor_hours",
        "Bring in the supervisor after",
        "int",
        "No-reply ladder",
        "Hours of silence before the case goes to the supervisor. Must be more than the "
        "reminder hours. Applies to new waits only.",
        2,
        168,
        "h",
    ),
    S(
        "no_reply_admin_hours",
        "Send to payroll after",
        "int",
        "No-reply ladder",
        "Hours the supervisor has before the case goes to payroll. Applies to new waits only.",
        1,
        168,
        "h",
    ),
    S(
        "scheduler_investigations_per_cycle",
        "Investigations per scheduler cycle",
        "int",
        "Scheduler",
        "LLM investigations the scheduler may start in one cycle. 0 pauses them.",
        0,
        5,
    ),
    S(
        "scheduler_messages_per_cycle",
        "Worker messages per scheduler cycle",
        "int",
        "Scheduler",
        "Worker questions the scheduler may send in one cycle. 0 pauses them.",
        0,
        10,
    ),
    S(
        "briefing_min_interval_seconds",
        "Minimum time between briefing refreshes",
        "int",
        "Daily briefing",
        "Seconds between two briefing refreshes of the same scope.",
        60,
        3600,
        "s",
    ),
    S(
        "briefing_max_llm_calls_per_day",
        "Briefing LLM calls per day",
        "int",
        "Daily briefing",
        "LLM calls the briefing may make in one day. 0 = template only.",
        0,
        100,
    ),
    S(
        "briefing_scheduled",
        "Scheduled daily briefing",
        "bool",
        "Daily briefing",
        "The scheduler writes Priya's briefing once per workflow day.",
    ),
    S(
        "overtime_warning_margin_hours",
        "Overtime warning margin",
        "half",
        "Dashboard",
        "Workers within this many hours of the P5 weekly limit show on the dashboard. "
        "Must be below the P5 limit.",
        0.5,
        20,
        "h",
    ),
)
SPECS: dict[str, Spec] = {s.key: s for s in EDITABLE}

# Shown by GET as read-only (set by the server configuration). Never editable here.
READ_ONLY: tuple[Spec, ...] = (
    S(
        "no_reply_escalation_enabled",
        "No-reply ladder",
        "bool",
        "No-reply ladder",
        "Kill switch for the whole ladder.",
    ),
    S("scheduler_enabled", "Scheduler timer", "bool", "Scheduler", "Starts the timer at boot."),
    S(
        "scheduler_interval_seconds",
        "Scheduler interval",
        "half",
        "Scheduler",
        "Seconds between timer cycles.",
        unit="s",
    ),
    S(
        "scheduler_backlog",
        "Scheduler works the backlog",
        "bool",
        "Scheduler",
        "Also process cases detected before the watermark.",
    ),
    S(
        "briefing_enabled",
        "LLM briefing",
        "bool",
        "Daily briefing",
        "Off = template briefing only.",
    ),
)
READ_ONLY_KEYS = {s.key for s in READ_ONLY}
LOCKED_NOTE = "Set by the server configuration; it cannot be changed while the app runs."
POLICY_KEY = re.compile(r"^(policy|policy_json|p\d{1,2})([._].*)?$", re.IGNORECASE)
SETTINGS_FIELDS = {f.name for f in fields(Settings)}


# ------------------------------------------------------------------ reading


def code_default(key: str) -> Any:
    for f in fields(Settings):
        if f.name == key:
            return f.default
    raise KeyError(key)


def _normal(spec: Spec, value: Any) -> Any:
    """The comparable form of a value (env floats like 8.0 match an override of 8)."""
    if spec.kind == "bool":
        return bool(value)
    number = float(value)
    return int(number) if spec.kind == "int" and number.is_integer() else number


def load_overrides(session: Session) -> dict[str, Any]:
    row = session.get(SettingRow, OVERRIDES_KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    return {k: v for k, v in value.items() if k in SPECS}


def apply_overrides(base: Settings, overrides: dict[str, Any]) -> Settings:
    """The effective settings. A stored value that no longer fits (for example after the
    server's environment changed) is skipped and logged, never fatal."""
    if not overrides:
        return base
    try:
        return replace(base, **overrides)
    except (TypeError, ValueError):
        effective = base
        for key, value in overrides.items():
            try:
                effective = replace(effective, **{key: value})
            except (TypeError, ValueError):
                log.warning(
                    "stored setting override skipped",
                    extra={"event": "settings_override_skipped", "key": key},
                )
        return effective


class SettingsReader:
    """Builds the effective settings for one request or one scheduler cycle."""

    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions

    def apply(self, base: Settings) -> Settings:
        try:
            with self.sessions() as session:
                overrides = load_overrides(session)
        except SQLAlchemyError:
            log.warning(
                "settings overrides unreadable; using the server values",
                extra={"event": "settings_read_failed"},
            )
            return base
        return apply_overrides(base, overrides)


def source_of(key: str, base: Settings, overrides: dict[str, Any]) -> Source:
    if key in overrides:
        return "override"
    spec = SPECS.get(key) or next(s for s in READ_ONLY if s.key == key)
    same = _normal(spec, getattr(base, key)) == _normal(spec, code_default(key))
    return "default" if same else "env"


def changes_locked(base: Settings) -> bool:
    """The deployed Locked profile (deployed, demo mode off) refuses every change."""
    return base.deployed and not base.demo_mode


def profile_name(base: Settings) -> str:
    if not base.deployed:
        return "local"
    return "guided" if base.demo_mode else "locked"


# ------------------------------------------------------------------ text


def format_value(spec: Spec, value: Any) -> str:
    if value is None:
        return "not set"
    if spec.kind == "bool":
        return "on" if value else "off"
    number = _normal(spec, value)
    text = f"{number:g}" if isinstance(number, float) else str(number)
    return f"{text} {spec.unit}" if spec.unit else text


def range_text(spec: Spec) -> str | None:
    if spec.kind == "bool" or spec.minimum is None:
        return None
    step = " in steps of 0.5" if spec.kind == "half" else ""
    whole = "a whole number " if spec.kind == "int" else "a number "
    unit = f" {spec.unit}" if spec.unit else ""
    return f"{whole}from {spec.minimum:g} to {spec.maximum:g}{unit}{step}"


def _invalid(spec: Spec) -> InvalidSettingError:
    if spec.kind == "bool":
        message = f"{spec.label} must be true or false."
    else:
        message = f"{spec.label} must be {range_text(spec)}."
    return InvalidSettingError(message, details={"key": spec.key, "range": range_text(spec)})


# ------------------------------------------------------------------ validation


def resolve_key(key: str) -> Spec:
    """The spec of an editable key, or a clear refusal."""
    if key in SPECS:
        return SPECS[key]
    if key in SETTINGS_FIELDS or key in READ_ONLY_KEYS:
        raise ForbiddenError(
            f"{key} cannot be changed here. {LOCKED_NOTE}",
            code="setting_locked",
            details={"key": key},
        )
    if POLICY_KEY.match(key):
        raise ForbiddenError(
            "Policy rules and limits are fixed in policy.json and cannot be changed while "
            "the app runs.",
            code="setting_locked",
            details={"key": key},
        )
    raise NotFoundError(f"There is no setting called {key!r}.", code="unknown_setting")


def check_value(spec: Spec, value: Any) -> Any:
    """Strict type and range check. Returns the value to store (bool, int or float)."""
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise _invalid(spec)
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(spec)
    number = float(value)
    if not isfinite(number) or not (spec.minimum <= number <= spec.maximum):
        raise _invalid(spec)
    if spec.kind == "int":
        if not number.is_integer():
            raise _invalid(spec)
        return int(number)
    if not (number * 2).is_integer():
        raise _invalid(spec)
    return number


COMBINED = ("no_reply_reminder_hours", "no_reply_supervisor_hours", "overtime_warning_margin_hours")


def check_combination(values: dict[str, Any], policy: PolicyConfig, changed: Spec) -> None:
    """Rules across settings, checked on the values that would take effect, before the
    start-up checks in config.py (which name env variables) can run."""
    reminder = float(values["no_reply_reminder_hours"])
    supervisor = float(values["no_reply_supervisor_hours"])
    if reminder >= supervisor:
        first = (
            "the supervisor hours" if changed.key == "no_reply_reminder_hours" else "the reminder"
        )
        raise InvalidSettingError(
            f"The reminder ({reminder:g} h) must come before the supervisor is brought in "
            f"({supervisor:g} h). Change {first} first.",
            code="invalid_setting_combination",
            details={"key": changed.key},
        )
    limit = policy.number("P5", "weekly_overtime_after_hours")
    if float(values["overtime_warning_margin_hours"]) >= limit:
        raise InvalidSettingError(
            f"The overtime warning margin must be below the P5 weekly limit ({limit:g} h).",
            code="invalid_setting_combination",
            details={"key": changed.key},
        )


def check_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if len(text) < MIN_REASON:
        raise InvalidSettingError(
            f"Give a reason of at least {MIN_REASON} characters.", code="reason_required"
        )
    return text


def require_change_allowed(base: Settings) -> None:
    if changes_locked(base):
        raise ForbiddenError(
            "Settings cannot be changed in the Locked demo profile. They can still be read.",
            code="settings_locked_in_profile",
        )


def _combined(current: Settings, changes: dict[str, Any]) -> dict[str, Any]:
    return {k: changes.get(k, getattr(current, k)) for k in COMBINED}


def _build(current: Settings, changes: dict[str, Any], spec: Spec) -> Settings:
    """The settings that would take effect, through the same checks the server ran at
    start-up (config.py), as a last guard."""
    try:
        return replace(current, **changes)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(
            f"{spec.label} cannot take this value with the current settings.",
            code="invalid_setting_combination",
            details={"key": spec.key, "check": str(exc)[:200]},
        ) from None


# ------------------------------------------------------------------ writing


def _lock_overrides(session: Session, clock: Clock) -> SettingRow:
    session.execute(
        insert(SettingRow)
        .values(key=OVERRIDES_KEY, value={}, updated_at=clock.now())
        .on_conflict_do_nothing(index_elements=["key"])
    )
    return session.scalars(
        select(SettingRow).where(SettingRow.key == OVERRIDES_KEY).with_for_update()
    ).one()


def _side(spec: Spec, value: Any, source: Source) -> dict[str, Any]:
    return {"key": spec.key, "value": _normal(spec, value), "source": source}


def _audit(
    session: Session,
    clock: Clock,
    actor: EmployeeRow,
    *,
    action: str,
    before: dict,
    after: dict,
    reason: str,
) -> None:
    session.add(
        AuditLogRow(
            exception_id=None,
            actor="admin",
            actor_id=actor.employee_id,
            action=action,
            before=before,
            after=after,
            reason=reason,
            created_at=clock.now(),
        )
    )


def change(
    session: Session,
    clock: Clock,
    policy: PolicyConfig,
    base: Settings,
    actor_id: str,
    key: str,
    value: Any,
    reason: str | None,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    """Set an override. The caller holds the transaction."""
    require_change_allowed(base)  # first: the Locked profile refuses everyone alike
    actor = require_admin(session, actor_id)
    spec = resolve_key(key)
    new = check_value(spec, value)
    text = check_reason(reason)
    row = _lock_overrides(session, clock)
    overrides = {k: v for k, v in (row.value or {}).items() if k in SPECS}
    current = apply_overrides(base, overrides)
    old = getattr(current, key)
    if _normal(spec, old) == _normal(spec, new):
        raise ConflictError(f"{spec.label} is already {format_value(spec, old)}.", code="no_change")
    if key == "auto_resolve_enabled" and new is True and not confirm:
        raise InvalidSettingError(
            "Turning auto-resolve on closes low-risk exceptions without a person. Send "
            '"confirm": true to do it.',
            code="confirmation_required",
        )
    check_combination(_combined(current, {key: new}), policy, spec)
    _build(current, {key: new}, spec)
    before = _side(spec, old, source_of(key, base, overrides))
    row.value = {**overrides, key: new}
    row.updated_at = clock.now()
    after = _side(spec, new, "override")
    if key == "auto_resolve_enabled" and new is True:
        after["confirmed"] = True
    _audit(
        session, clock, actor, action="settings_changed", before=before, after=after, reason=text
    )
    log.info("setting changed", extra={"event": "settings_changed", "key": key})
    return {"key": key, "before": before, "after": after}


def reset(
    session: Session,
    clock: Clock,
    policy: PolicyConfig,
    base: Settings,
    actor_id: str,
    key: str,
    reason: str | None,
) -> dict[str, Any]:
    """Remove an override: back to the server's value. The caller holds the transaction."""
    require_change_allowed(base)  # first: the Locked profile refuses everyone alike
    actor = require_admin(session, actor_id)
    spec = resolve_key(key)
    text = check_reason(reason)
    row = _lock_overrides(session, clock)
    overrides = {k: v for k, v in (row.value or {}).items() if k in SPECS}
    if key not in overrides:
        raise ConflictError(
            f"{spec.label} has no change to reset; it already uses the server value.",
            code="no_override",
        )
    current = apply_overrides(base, overrides)
    old = getattr(current, key)
    rest = {k: v for k, v in overrides.items() if k != key}
    server = getattr(base, key)
    check_combination(_combined(current, {key: server}), policy, spec)
    _build(current, {key: server}, spec)
    row.value = rest
    row.updated_at = clock.now()
    before = _side(spec, old, "override")
    after = _side(spec, getattr(base, key), source_of(key, base, rest))
    _audit(session, clock, actor, action="settings_reset", before=before, after=after, reason=text)
    log.info("setting reset", extra={"event": "settings_reset", "key": key})
    return {"key": key, "before": before, "after": after}


# ------------------------------------------------------------------ views


def _history_item(entry: AuditLogRow, names: dict[str, str]) -> dict[str, Any]:
    before, after = entry.before or {}, entry.after or {}
    key = str(after.get("key") or before.get("key") or "")
    spec = SPECS.get(key)
    return {
        "id": entry.id,
        "at": entry.created_at,
        "action": entry.action,
        "key": key,
        "label": spec.label if spec else key,
        "actor_id": entry.actor_id,
        "actor_name": names.get(entry.actor_id or ""),
        "old_value": before.get("value"),
        "old_source": before.get("source"),
        "new_value": after.get("value"),
        "new_source": after.get("source"),
        "old_text": format_value(spec, before.get("value")) if spec else None,
        "new_text": format_value(spec, after.get("value")) if spec else None,
        "reason": entry.reason,
    }


def _names(session: Session) -> dict[str, str]:
    return {e.employee_id: e.name for e in session.scalars(select(EmployeeRow))}


def history(
    session: Session,
    actor_id: str,
    *,
    key: str | None = None,
    before_id: int | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    require_admin(session, actor_id)
    stmt = select(AuditLogRow).where(AuditLogRow.action.in_(HISTORY_ACTIONS))
    if key:
        stmt = stmt.where(AuditLogRow.after["key"].astext == key)
    if before_id is not None:
        stmt = stmt.where(AuditLogRow.id < before_id)
    rows = session.scalars(stmt.order_by(AuditLogRow.id.desc()).limit(limit + 1)).all()
    names = _names(session)
    items = [_history_item(r, names) for r in rows[:limit]]
    return {"items": items, "next_before_id": items[-1]["id"] if len(rows) > limit else None}


def _last_changes(session: Session) -> dict[str, AuditLogRow]:
    latest: dict[str, AuditLogRow] = {}
    rows = session.scalars(
        select(AuditLogRow)
        .where(AuditLogRow.action.in_(HISTORY_ACTIONS))
        .order_by(AuditLogRow.id.desc())
    )
    for row in rows:
        key = str((row.after or {}).get("key") or "")
        latest.setdefault(key, row)
    return latest


def _item(
    spec: Spec,
    base: Settings,
    effective: Settings,
    overrides: dict[str, Any],
    editable: bool,
    last: AuditLogRow | None,
    names: dict[str, str],
) -> dict[str, Any]:
    value = getattr(effective, spec.key)
    within = (
        spec.kind == "bool"
        or spec.minimum is None
        or spec.minimum <= float(value) <= (spec.maximum or float("inf"))
    )
    return {
        "key": spec.key,
        "label": spec.label,
        "group": spec.group,
        "help": spec.help,
        "kind": spec.kind,
        "value": _normal(spec, value),
        "value_text": format_value(spec, value),
        "source": source_of(spec.key, base, overrides),
        "server_value": _normal(spec, getattr(base, spec.key)),
        "default_value": _normal(spec, code_default(spec.key)),
        "env_var": spec.env,
        "editable": editable,
        "minimum": spec.minimum if editable else None,
        "maximum": spec.maximum if editable else None,
        "unit": spec.unit,
        "range_text": range_text(spec) if editable else None,
        "within_range": within,
        "needs_confirm_to_enable": spec.key == "auto_resolve_enabled",
        "locked_note": None if editable else LOCKED_NOTE,
        "last_change": _history_item(last, names) if last is not None else None,
    }


def overview(session: Session, base: Settings, actor_id: str) -> dict[str, Any]:
    """GET /api/settings: every editable setting plus the read-only ones."""
    require_admin(session, actor_id)
    overrides = load_overrides(session)
    effective = apply_overrides(base, overrides)
    last = _last_changes(session)
    names = _names(session)
    items = [_item(s, base, effective, overrides, True, last.get(s.key), names) for s in EDITABLE]
    items += [_item(s, base, effective, overrides, False, None, names) for s in READ_ONLY]
    locked = changes_locked(base)
    return {
        "profile": profile_name(base),
        "changes_allowed": not locked,
        "locked_reason": (
            "The Locked demo profile is read-only. Settings can be changed in the Guided "
            "profile or in local development."
            if locked
            else None
        ),
        "min_reason_length": MIN_REASON,
        "items": items,
    }
