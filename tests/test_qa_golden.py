"""Phase 20: the golden question set (tests/qa_golden.json), run on the seeded demo.

Each question runs twice: once with no LLM (template answers and code refusals) and once
with a scripted model that replays the item's `model_answer` (and `intent_reply`). The
scripted path checks that the expected answer passes every grounding check on the first
draft, that refusals make no LLM call, and that the facts packet stays small and holds
only Amit's data. Phase 23 reuses the file for the real-model evaluation.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from attendflow.qa.facts import PACKET_LIMIT
from attendflow.qa.intents import INTENTS, REFUSALS
from tests.api_helpers import AMIT
from tests.test_qa_api import KEY, OTHER_IDS, _add_p17, app_client, ask, use_model

GOLDEN = json.loads((Path(__file__).parent / "qa_golden.json").read_text(encoding="utf-8"))
ITEMS = GOLDEN["questions"]


def test_the_golden_file_is_well_formed():
    assert 15 <= len(ITEMS) <= 20
    ids = [item["id"] for item in ITEMS]
    assert len(ids) == len(set(ids))
    kinds = {item["expect"]["kind"] for item in ITEMS}
    assert kinds == {"answer", "refusal"}
    for item in ITEMS:
        expect = item["expect"]
        assert set(expect.get("intents", [])) <= set(INTENTS), item["id"]
        if expect["kind"] == "refusal":
            assert expect["refusal_code"] in REFUSALS and "model_answer" not in item
        else:
            assert item["model_answer"]["answer"], item["id"]
    # Setups run last, so they never change the facts of an earlier question.
    assert all("setup" not in i for i in ITEMS[: len([i for i in ITEMS if "setup" not in i])])


def _setup(client, item) -> None:
    if item.get("setup") == "p17_monday":
        _add_p17(client, date(2026, 4, 13))


def _check(body: dict, expect: dict, item_id: str) -> None:
    assert body["kind"] == expect["kind"], (item_id, body)
    if expect["kind"] == "refusal":
        assert body["refusal_code"] == expect["refusal_code"], (item_id, body)
        assert body["llm_calls"] == 0, item_id
    else:
        assert body["intents"] == expect["intents"], (item_id, body["intents"])
    if "exact" in expect:
        assert body["answer"] == expect["exact"], item_id
    for text in expect.get("must_not_contain", []):
        assert text not in body["answer"], (item_id, text, body["answer"])


def test_golden_questions_without_an_llm(db_engine):
    with app_client(db_engine, qa_questions_per_hour=30) as c:
        for item in ITEMS:
            _setup(c, item)
            body = ask(c, item["question"], actor=AMIT)
            expect = item.get("expect_offline", item["expect"])
            _check(body, expect, item["id"])
            if expect["kind"] == "answer":
                assert body["source"] == "template" and body["sources"], item["id"]
                for fact in expect.get("facts", []):
                    assert fact in body["answer"], (item["id"], fact, body["answer"])


def test_golden_questions_with_a_scripted_model(db_engine, monkeypatch):
    with app_client(db_engine, llm_api_key=KEY, qa_questions_per_hour=30) as c:
        for item in ITEMS:
            _setup(c, item)
            replies = [r for r in (item.get("intent_reply"), item.get("model_answer")) if r]
            script = use_model(monkeypatch, *replies)
            body = ask(c, item["question"], actor=AMIT)
            _check(body, item["expect"], item["id"])
            if item["expect"]["kind"] == "refusal":
                assert script.calls == [], item["id"]
                continue
            assert (body["source"], body["reason"]) == ("llm", "validated"), (item["id"], body)
            assert body["answer"] == item["model_answer"]["answer"]
            assert len(script.calls) == len(replies)
            facts = json.loads(script.calls[-1][1]["content"])["facts"]
            text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
            assert len(text) <= PACKET_LIMIT, (item["id"], len(text))
            assert facts["you"]["employee_id"] == "E001"
            assert not [eid for eid in OTHER_IDS if eid in text], item["id"]
