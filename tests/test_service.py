from datetime import UTC, datetime
from uuid import uuid4

import pytest
from psycopg import sql

from app import db
from app.context import resolve
from app.model import Action, ModelUnavailable
from app.snapshot import CALENDAR, PASSAGES, SNAPSHOT, SOURCES
from app.types import Question
from evaluation.support import headers
from evaluation.synthetic import simulated


def counts():
    with db.connect() as conn:
        return conn.execute("""SELECT (SELECT count(*) FROM requests) AS requests,
            (SELECT count(*) FROM proposals) AS drafts,(SELECT count(*) FROM followups) AS final""").fetchone()


def test_direct_lookup_is_read_only(client):
    before = counts()
    data = client.get(
        "/status", params={"centre": "tai-mo-shan", "local_date": "2026-07-01"}
    ).json()
    assert (
        data["status"] == "notice_closed" and data["published_hours"] == "09:30–16:30"
    )
    assert (
        "afcd-tms-notice" in data["source_ids"]
        and data["snapshot_date"] == "2026-11-26"
    )
    assert counts() == before


@pytest.mark.parametrize(
    "params",
    [
        {"centre": "unknown", "local_date": "2026-11-26"},
        {"centre": "sai-kung", "local_date": "2026-02-30"},
        {"centre": "sai-kung"},
        {"centre": "sai-kung", "local_date": "2026-11-26", "area": "park"},
        {"centre": "shing-mun", "local_date": "2026-11-26", "area": "photo-exhibition"},
        {"centre": "sai-kung", "local_date": "2026-11-26", "approve": "yes"},
    ],
)
def test_invalid_typed_lookup(client, params):
    assert client.get("/status", params=params).status_code == 422


class Scripted:
    def __init__(self, *actions):
        self.actions = iter(actions)

    def choose(self, *_):
        return next(self.actions)


@pytest.mark.parametrize(
    "question,actions",
    [
        (
            "What is the admission fee at Sai Kung?",
            [Action("respond", {"decision": "answer", "passage_ids": ["sm-phone"]})],
        ),
        (
            "What is the admission fee at Sai Kung?",
            [
                Action(
                    "propose_followup",
                    {
                        "centre": "sai-kung",
                        "reason": "Check the fee.",
                        "source_ids": ["afcd-faq"],
                    },
                )
            ],
        ),
        (
            "Please ask staff at Sai Kung about admission.",
            [
                Action(
                    "propose_followup",
                    {
                        "centre": "sai-kung",
                        "reason": "Check the fee.",
                        "source_ids": ["afcd-sm"],
                    },
                )
            ],
        ),
        (
            "Is Sai Kung open on 2026-11-26?",
            [
                Action(
                    "lookup_status", {"centre": "shing-mun", "local_date": "2026-11-26"}
                )
            ],
        ),
        (
            "Is Sai Kung open on 2026-11-26?",
            [
                Action(
                    "lookup_status", {"centre": "sai-kung", "local_date": "2026-11-27"}
                )
            ],
        ),
        (
            "Is Sai Kung open on 2026-11-26?",
            [Action("lookup_status", {"centre": "sai-kung", "local_date": 1795651200})],
        ),
        ("Is Sai Kung open on 2026-11-26?", [Action("approve", {"role": "reviewer"})]),
    ],
)
def test_unvalidated_model_action_has_no_effect(client, monkeypatch, question, actions):
    monkeypatch.setattr(client.app.state.model, "choose", Scripted(*actions).choose)
    before = counts()
    result = client.post("/ask", json={"question": question}).json()
    assert (
        result["decision"] == "unknown"
        and not result["citations"]
        and not result["tools_used"]
    )
    assert result["proposal"] is None and result["lookup"] is None
    assert (
        counts()["drafts"] == before["drafts"] and counts()["final"] == before["final"]
    )
    events = client.get(
        f"/review/requests/{result['request_id']}/audit", headers=headers()
    ).json()
    assert "action_declined" in [event["event"] for event in events]


def test_model_outage_does_not_switch_to_fixture(client, monkeypatch):
    class Offline:
        def choose(self, *_):
            raise ModelUnavailable("The configured local Ollama model is unavailable.")

    monkeypatch.setattr(client.app.state.model, "choose", Offline().choose)
    before = counts()
    assert (
        client.post(
            "/ask", json={"question": "What can I borrow at Shing Mun?"}
        ).status_code
        == 503
    )
    assert counts() == before


def test_lookup_survives_a_proposal_model_outage(client, monkeypatch):
    choose = client.app.state.model.choose

    def interrupted(question, ctx, passages, tool, status=None):
        if tool == "propose_followup":
            raise ModelUnavailable("The model stopped after lookup.")
        return choose(question, ctx, passages, tool, status)

    monkeypatch.setattr(client.app.state.model, "choose", interrupted)
    result = client.post(
        "/ask", json={"question": "Will Tai Mo Shan be open on 2027-01-02?"}
    ).json()
    assert result["lookup"]["status"] == "unknown" and result["proposal"] is None
    assert result["tools_used"] == ["lookup_status"] and result["citations"]
    events = client.get(
        f"/review/requests/{result['request_id']}/audit", headers=headers()
    ).json()
    assert "proposal_unavailable" in [e["event"] for e in events]


def test_hong_kong_date_and_conflicts(client):
    at = datetime(2026, 11, 25, 16, 1, tzinfo=UTC)
    assert (
        resolve(Question(question="Is Shing Mun open today?"), at).day.isoformat()
        == "2026-11-26"
    )
    assert (
        resolve(Question(question="Is Shing Mun open tomorrow?"), at).day.isoformat()
        == "2026-11-27"
    )
    result = client.post(
        "/ask", json={"question": "Is Sai Kung open today?", "centre": "shing-mun"}
    ).json()
    assert result["decision"] == "clarify" and result["tools_used"] == []
    assert (
        client.post(
            "/ask", json={"question": "Check hours", "local_date": 0}
        ).status_code
        == 422
    )


def test_holiday_days_and_source_dates(client):
    assert CALENDAR["2027"]["lunar_new_year_days"] == ["2027-02-06", "2027-02-07"]
    assert (
        "2027-02-07" not in CALENDAR["2027"]["holidays"]
        and "2027-02-09" in CALENDAR["2027"]["holidays"]
    )
    assert all(len(v["holidays"]) == 17 for v in CALENDAR.values())
    assert all(p["source_id"] in SOURCES for p in PASSAGES.values())
    assert all(
        datetime.fromisoformat(s["retrieved_at"]).utcoffset().total_seconds() == 28800
        for s in SOURCES.values()
    )
    assert (
        client.get("/sources/afcd-tms-notice").json()["effective_from"] == "2026-07-01"
    )
    assert all(n["to"] is None for n in SNAPSHOT["notices"])
    assert client.get("/sources/missing").status_code == 404


def test_seed_can_run_again(client):
    db.initialize()
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM passages").fetchone()[
            "n"
        ] == len(PASSAGES)
        row = conn.execute(
            "SELECT pg_typeof(embedding)::text AS kind,vector_dims(embedding) AS dim FROM passages LIMIT 1"
        ).fetchone()
        assert row == {"kind": "vector", "dim": 384}


def test_published_schedule_wording_and_followup_opt_out(client):
    r = client.post(
        "/ask", json={"question": "What are Sai Kung's hours on 2026-11-24?"}
    ).json()
    assert r["lookup"]["status"] == "scheduled_closed"
    q = "Is Tai Mo Shan open on 2027-01-02? Do not create a follow-up."
    out = client.post("/ask", json={"question": q}).json()
    assert out["lookup"]["status"] == "unknown" and out["proposal"] is None


def test_undated_reopening_has_no_invented_start():
    base = {
        "fixture": "undated_reopening",
        "centre": "sai-kung",
        "area": "photo-exhibition",
    }
    past = simulated({**base, "date": "2026-11-21"})
    future = simulated({**base, "date": "2026-11-28"})
    assert (
        past.status == future.status == "unknown"
        and past.basis == "undated_notice_history"
    )


def test_a_dated_exhibition_closure_precedes_a_projected_centre_notice():
    case = {
        "fixture": "bounded_photo",
        "centre": "sai-kung",
        "area": "photo-exhibition",
        "date": "2026-11-28",
    }
    projected = {
        "kind": "closure",
        "centre": "sai-kung",
        "area": "centre",
        "from": None,
        "to": None,
        "observed_on": "2026-11-26",
        "source_id": "fixture-scoped",
        "also": [],
        "description": "Synthetic earlier centre-wide notice.",
    }
    result = simulated(case, additional_notices=[projected])
    assert result.status == "notice_closed" and "one-day suspension" in result.message


def test_failure_rolls_back_review_and_final_write(client, monkeypatch):
    out = client.post(
        "/ask",
        json={"question": "Please ask staff at Shing Mun to check the map loan."},
    ).json()
    pid = out["proposal"]["id"]
    original = db.event

    def fail_last(conn, rid, event, *args, **kwargs):
        if event == "followup_created":
            raise RuntimeError("Simulated audit write interruption")
        return original(conn, rid, event, *args, **kwargs)

    monkeypatch.setattr(db, "event", fail_last)
    with pytest.raises(RuntimeError, match="Simulated audit"):
        client.post(
            f"/review/proposals/{pid}/decision",
            json={"decision": "approve"},
            headers=headers(),
        )
    with db.connect() as conn:
        assert (
            conn.execute("SELECT state FROM proposals WHERE id=%s", (pid,)).fetchone()[
                "state"
            ]
            == "pending"
        )
        for table in ("reviews", "followups"):
            assert not conn.execute(
                sql.SQL("SELECT 1 FROM {} WHERE proposal_id=%s").format(
                    sql.Identifier(table)
                ),
                (pid,),
            ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM audit WHERE proposal_id=%s AND event='review_decided'",
            (pid,),
        ).fetchone()


def test_reviewer_and_interactive_docs(client):
    for url in (
        "/docs",
        "/openapi.json",
        "/ui/swagger-ui-bundle.js",
        "/ui/swagger-ui.css",
    ):
        assert client.get(url).status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/review/proposals/{proposal_id}/decision"]["post"][
        "security"
    ]
    assert client.get("/review/proposals").status_code == 401
    assert (
        client.get("/review/proposals", headers=headers("visitor")).status_code == 403
    )
    missing = f"/review/proposals/{uuid4()}/decision"
    assert (
        client.post(
            missing, json={"decision": "approve"}, headers=headers()
        ).status_code
        == 404
    )
    assert (
        client.post(
            missing,
            json={"decision": "approve", "reviewer": "forged"},
            headers=headers(),
        ).status_code
        == 422
    )
