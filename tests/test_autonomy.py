"""Phase 14 anti-drift tests for the Autonomy Table (backend/attendflow/activity/autonomy.py).

1. Every audit action any code path can write is a registry row, and every registry action
   is written somewhere (a static scan of the backend). The runtime half (every audit row
   the whole suite writes) is the conftest listener, self-tested here.
2. Every row that needs a person names real tests that assert the refusal or the
   data-safety rule; every "never" row names real tests.
3. The README section is the registry's own output.
(The "autonomous rows really happen with their actor" test runs the end-to-end story in
tests/test_activity.py.)
"""

from __future__ import annotations

import ast
import itertools
import re
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from attendflow.activity import autonomy
from attendflow.config import REPO_ROOT
from attendflow.db.models import ACTORS, AuditLogRow, Base
from attendflow.scripts import autonomy_cli
from attendflow.tools.registry import TOOLS
from tests import audit_guard

BACKEND = REPO_ROOT / "backend" / "attendflow"
WRITER_CALLS = ("AuditLogRow", "_audit", "audit")
HUMAN_AUDIT_ACTORS = ("worker", "supervisor", "admin")
# A named "approval" test must visibly assert a refusal or a data-safety rule.
REFUSAL_MARKERS = (
    "assert_error(",
    "status_code == 403",
    "status_code == 404",
    "status_code == 409",
    "snapshot(",
    "write_log",
    "pytest.raises(",
)


# ---------------------------------------------------------------- 1. static scan


class _Unresolvable(Exception):
    pass


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _action_arg(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "action":
            return kw.value
    if name == "_audit" and len(call.args) > 2:  # scheduler/cycle.py: (deps, id, action, ...)
        return call.args[2]
    if name == "audit" and call.args:  # agent/journal.py: journal.audit(action, ...)
        return call.args[0]
    return None


def _literal_values(annotation: ast.expr | None) -> list[str] | None:
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Literal"
    ):
        items = (
            annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        )
        return [i.value for i in items if isinstance(i, ast.Constant)]
    return None


def _resolve(expr: ast.expr, func: ast.FunctionDef | None) -> set[str] | None:
    """The action names an expression can take; None = a parameter (its callers are
    scanned instead). Anything else fails, so audit actions stay statically known."""
    params = {a.arg: a for a in (func.args.args + func.args.kwonlyargs)} if func else {}
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    if isinstance(expr, ast.IfExp):
        return (_resolve(expr.body, func) or set()) | (_resolve(expr.orelse, func) or set())
    if isinstance(expr, ast.JoinedStr):
        pieces: list[list[str]] = []
        for part in expr.values:
            if isinstance(part, ast.Constant):
                pieces.append([part.value])
            elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name):
                arg = params.get(part.value.id)
                values = _literal_values(arg.annotation) if arg else None
                if not values:
                    raise _Unresolvable(f"f-string uses {part.value.id!r} without a Literal type")
                pieces.append(values)
            else:
                raise _Unresolvable(ast.unparse(expr))
        return {"".join(p) for p in itertools.product(*pieces)}
    if isinstance(expr, ast.Name):
        if expr.id in params:
            return None
        found: set[str] = set()
        for node in ast.walk(func) if func else []:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == expr.id for t in node.targets
            ):
                found |= _resolve(node.value, func) or set()
        if found:
            return found
    raise _Unresolvable(ast.unparse(expr))


def scan_audit_actions() -> dict[str, list[str]]:
    """action -> ['file:line', ...] for every audit write in the backend."""
    found: dict[str, list[str]] = {}
    for path in sorted(BACKEND.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _callee(node) not in WRITER_CALLS:
                continue
            name = _callee(node)
            expr = _action_arg(node, name)
            if expr is None:
                continue
            owner = min(
                (f for f in funcs if f.lineno <= node.lineno <= (f.end_lineno or 0)),
                key=lambda f: (f.end_lineno or 0) - f.lineno,
                default=None,
            )
            where = f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}"
            try:
                values = _resolve(expr, owner)
            except _Unresolvable as exc:
                pytest.fail(f"{where}: audit action is not statically known ({exc})")
            for value in values or ():
                found.setdefault(value, []).append(where)
    return found


def test_every_audit_action_in_the_code_is_in_the_registry():
    in_code = scan_audit_actions()
    assert len(in_code) > 40  # the scan really found the writers
    missing = {a: w for a, w in in_code.items() if a not in autonomy.registered_actions()}
    assert not missing, f"add these audit actions to activity/autonomy.py: {missing}"
    stale = autonomy.registered_actions() - set(in_code)
    assert not stale, f"registry actions that no code writes: {sorted(stale)}"


def test_the_scan_catches_unknown_and_dynamic_actions(tmp_path):
    good = ast.parse('def f(after: Literal["a", "b"]):\n    _audit(x, action=f"p_{after}")')
    call = next(n for n in ast.walk(good) if isinstance(n, ast.Call))
    assert _resolve(_action_arg(call, "_audit"), good.body[0]) == {"p_a", "p_b"}
    bad = ast.parse(
        "def f(after: str):\n    _audit(x, action=f'p_{after}')\n    _audit(x, action=g())"
    )
    func = bad.body[0]
    for call in [n for n in ast.walk(bad) if isinstance(n, ast.Call) and _callee(n) == "_audit"]:
        with pytest.raises(_Unresolvable):
            _resolve(_action_arg(call, "_audit"), func)


def test_every_audit_row_written_by_the_tests_is_in_the_registry(client):
    """The runtime half: conftest listens to every AuditLogRow insert of the session and
    fails the test that wrote an unmapped (action, actor) pair. Self-test: an unmapped row
    is caught, a mapped one is not."""
    start = len(audit_guard.UNMAPPED)
    with Session(client.app.state.engine) as s, s.begin():
        s.add(AuditLogRow(actor="system", action="detected", created_at=_now()))
        s.add(AuditLogRow(actor="worker", action="approve", created_at=_now()))
        s.add(AuditLogRow(actor="system", action="phase14_not_in_the_table", created_at=_now()))
    caught = audit_guard.UNMAPPED[start:]
    del audit_guard.UNMAPPED[start:]  # handled here, so the teardown check stays green
    assert caught == [("approve", "worker"), ("phase14_not_in_the_table", "system")]


def _now():
    from datetime import datetime

    return datetime(2026, 4, 16, 8)


# ---------------------------------------------------------------- 2. the rows themselves


def test_registry_rows_are_well_formed():
    keys = [c.key for c in autonomy.CAPABILITIES]
    assert len(keys) == len(set(keys))
    for c in autonomy.CAPABILITIES:
        assert c.guardrail.endswith(".") and len(c.guardrail) <= 260, c.key
        if c.kind == "never":
            assert not c.audit_actions and c.proof_tests, c.key
            continue
        assert c.audit_actions and c.audit_actors, c.key
        assert set(c.audit_actors) <= set(ACTORS), c.key
        if c.actor_type == "human":
            assert set(c.audit_actors) - {"system"} <= set(HUMAN_AUDIT_ACTORS), c.key
            assert not c.autonomous
        else:
            assert set(c.audit_actors) <= set(autonomy.AUTONOMOUS_AUDIT_ACTORS), c.key
            assert c.approval == "none" and c.autonomous, c.key
    # The one action that both the scheduler and a person write is told apart by actor.
    assert autonomy.capability_for("ask_worker", "system").key == "auto_ask_worker"
    assert autonomy.capability_for("ask_worker", "supervisor").key == "ask_worker"
    assert autonomy.capability_for("ask_worker", "worker") is None


def _row(key: str) -> autonomy.Capability:
    return next(c for c in autonomy.CAPABILITIES if c.key == key)


def test_phase_12_and_13_rows_have_the_agreed_actor_approval_and_guardrail():
    auto = _row("auto_resolve")
    assert (auto.actor_type, auto.approval, auto.reversible) == ("code", "none", "yes_undo")
    assert "P2" in auto.guardrail and "P7" in auto.guardrail
    assert "AUTO_RESOLVE_ENABLED" in auto.guardrail
    undo = _row("undo_auto_resolve")
    assert (undo.actor_type, undo.approval) == ("human", "supervisor_or_payroll_admin")
    assert "refused" in undo.guardrail
    for key, hours in [
        ("no_reply_reminder", "NO_REPLY_REMINDER_HOURS"),
        ("no_reply_to_supervisor", "NO_REPLY_SUPERVISOR_HOURS"),
        ("no_reply_to_admin", "NO_REPLY_ADMIN_HOURS"),
    ]:
        step = _row(key)
        assert (step.actor_type, step.approval, step.audit_actors) == (
            "system",
            "none",
            ("system",),
        )
        assert hours in step.guardrail
        assert "data" in step.guardrail  # every ladder step says it changes no data
    without = _row("decide_without_worker")
    assert (without.actor_type, without.approval, without.reversible) == (
        "human",
        "supervisor_or_payroll_admin",
        "no",
    )
    assert "10+" in without.guardrail and "tick" in without.guardrail
    assert _row("never_silence_consent").kind == "never"


def _test_source(node_id: str) -> str:
    file, name = node_id.split("::")
    path = REPO_ROOT / file
    assert path.is_file(), f"{node_id}: no such file"
    source = path.read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    pytest.fail(f"{node_id}: no such test")


@pytest.mark.parametrize(
    "row",
    [c for c in autonomy.CAPABILITIES if c.kind == "allowed" and c.approval != "none"],
    ids=lambda c: c.key,
)
def test_rows_that_need_a_person_name_tests_that_prove_the_refusal(row):
    assert row.proof_tests, f"{row.key}: name the tests that prove the approval"
    for node_id in row.proof_tests:
        source = _test_source(node_id)
        assert any(m in source for m in REFUSAL_MARKERS), (
            f"{node_id} does not assert a refusal (403/404/409) or a data-safety rule"
        )


@pytest.mark.parametrize(
    "row", [c for c in autonomy.CAPABILITIES if c.kind == "never"], ids=lambda c: c.key
)
def test_never_rows_name_real_tests(row):
    for node_id in row.proof_tests:
        source = _test_source(node_id)
        assert "assert" in source or "pytest.raises(" in source, node_id


PAY_WORDS = re.compile(r"salary|wage|pay_?rate|hourly_rate|gross|net_pay|payslip|payroll_amount")


def test_never_payroll_no_pay_data_and_no_pay_tool():
    """The app cleans attendance only: no table column holds pay, no tool computes it."""
    columns = [f"{t.name}.{c.name}" for t in Base.metadata.tables.values() for c in t.columns]
    assert columns and not [c for c in columns if PAY_WORDS.search(c)]
    names = list(TOOLS)
    assert names and not [n for n in names if PAY_WORDS.search(n) or "pay" in n]


# ---------------------------------------------------------------- 3. the README copy


def test_readme_autonomy_table_is_up_to_date():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert autonomy.README_START in readme and autonomy.README_END in readme
    assert autonomy.render_readme(readme) == readme, (
        "README.md is out of date: run `python -m uv run attendflow-autonomy --write-readme`"
    )
    for c in autonomy.CAPABILITIES:
        assert c.title in readme


def test_cli_prints_checks_and_writes(tmp_path: Path, capsys):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# X\n\n{autonomy.README_START}\nSTALE-TABLE\n{autonomy.README_END}\n\nafter\n",
        encoding="utf-8",
    )
    assert autonomy_cli.main([]) == 0
    assert "| Auto-resolve a low-risk exception |" in capsys.readouterr().out
    assert autonomy_cli.main(["--check", "--readme", str(readme)]) == 1
    assert autonomy_cli.main(["--write-readme", "--readme", str(readme)]) == 0
    text = readme.read_text(encoding="utf-8")
    assert "STALE-TABLE" not in text and text.endswith(f"{autonomy.README_END}\n\nafter\n")
    assert autonomy_cli.main(["--check", "--readme", str(readme)]) == 0
    readme.write_text("# no markers\n", encoding="utf-8")
    assert autonomy_cli.main(["--check", "--readme", str(readme)]) == 1
