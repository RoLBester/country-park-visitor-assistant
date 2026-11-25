import pytest

from app import db
from app.model import Action
from evaluation.support import headers


@pytest.mark.parametrize(
    "date_text,local_date,prompt",
    [
        ("7 February", None, "year"),
        ("February 7th", None, "year"),
        ("07/02", None, "YYYY-MM-DD"),
        ("02-07-2027", None, "YYYY-MM-DD"),
        ("the 7th", None, "YYYY-MM-DD"),
        ("February", None, "year"),
        ("7 February", "2027-02-08", "single"),
    ],
)
def test_date_needs_clarification_before_any_action(
    client, monkeypatch, date_text, local_date, prompt
):
    calls = []
    choose = client.app.state.model.choose

    def record(*args):
        calls.append(args[3])
        return choose(*args)

    monkeypatch.setattr(client.app.state.model, "choose", record)
    question = f"What are Sai Kung’s opening hours on {date_text}? Please ask staff."
    reply = client.post(
        "/ask", json={"question": question, "local_date": local_date}
    ).json()
    assert not calls
    assert reply["decision"] == "clarify" and prompt in reply["answer"]
    assert (
        reply["tools_used"] == reply["selected_passage_ids"] == reply["citations"] == []
    )
    assert reply["lookup"] is reply["proposal"] is None
    audit = client.get(
        f"/review/requests/{reply['request_id']}/audit", headers=headers()
    ).json()
    assert [row["event"] for row in audit] == ["retrieved", "reply"]
    with db.connect() as conn:
        assert not conn.execute(
            "SELECT id FROM proposals WHERE request_id=%s", (reply["request_id"],)
        ).fetchone()


@pytest.mark.parametrize(
    "date_text,local_date",
    [("February 7th, 2027", None), ("7 February", "2027-02-07")],
)
def test_complete_date_uses_typed_lookup(client, date_text, local_date):
    reply = client.post(
        "/ask",
        json={
            "question": f"What are Sai Kung’s opening hours on {date_text}?",
            "local_date": local_date,
        },
    ).json()
    assert reply["decision"] == "status" and reply["tools_used"] == ["lookup_status"]
    assert (
        reply["lookup"]["local_date"] == "2027-02-07"
        and reply["lookup"]["status"] == "scheduled_closed"
    )
    assert {c["source_id"] for c in reply["citations"]} == {
        "afcd-sk",
        "hko-2027",
        "hk-1823",
    }
    assert reply["proposal"] is None


@pytest.mark.parametrize(
    "day,status,basis,draft",
    [
        ("2026-11-26", "notice_closed", "closure_notice", False),
        ("2027-02-07", "scheduled_closed", "lunar_days_1_2", False),
        ("2027-01-05", "scheduled_closed", "ordinary_tuesday", False),
        ("2027-01-02", "unknown", "after_notice_observation", True),
    ],
)
def test_tai_mo_shan_schedule_and_renovation(client, day, status, basis, draft):
    direct = client.get(
        "/status", params={"centre": "tai-mo-shan", "local_date": day}
    ).json()
    reply = client.post(
        "/ask", json={"question": f"Is Tai Mo Shan open on {day}?"}
    ).json()
    assert reply["decision"] == "status" and reply["lookup"] == direct
    assert (direct["status"], direct["basis"]) == (status, basis)
    assert {c["source_id"] for c in reply["citations"]} == {
        "afcd-tms",
        "afcd-tms-notice",
        "hk-1823",
        f"hko-{day[:4]}",
    }
    (notice,) = direct["notices"]
    assert (notice["area"], notice["from"], notice["observed_on"], notice["to"]) == (
        "centre",
        "2026-07-01",
        "2026-11-26",
        None,
    )
    if status == "scheduled_closed":
        assert direct["published_hours"] is None
        assert all(
            term in direct["message"].lower()
            for term in ("renovation", "2026-11-26", "reopening", "unconfirmed")
        )
    assert reply["tools_used"] == (
        ["lookup_status", "propose_followup"] if draft else ["lookup_status"]
    )
    assert (reply["proposal"]["state"] if reply["proposal"] else None) == (
        "pending" if draft else None
    )


@pytest.mark.parametrize(
    "selected", [["tms-access"], ["tms-closure", "tms-access"], ["tms-closure"], []]
)
def test_shared_facility_answer_includes_notice_once(client, monkeypatch, selected):
    model_decision = "answer" if selected else "unknown"

    def choose(*_):
        return Action("respond", {"decision": model_decision, "passage_ids": selected})

    monkeypatch.setattr(client.app.state.model, "choose", choose)
    reply = client.post(
        "/ask", json={"question": "Can I use the accessible toilet at Tai Mo Shan?"}
    ).json()
    assert reply["decision"] == "answer"
    assert sorted(reply["selected_passage_ids"]) == ["tms-access", "tms-closure"]
    assert {c["source_id"] for c in reply["citations"]} == {
        "afcd-tms",
        "afcd-tms-notice",
    }
    assert "accessible toilet" in reply["answer"] and "1 July 2026" in reply["answer"]
    assert reply["tools_used"] == [] and reply["proposal"] is None
    audit = client.get(
        f"/review/requests/{reply['request_id']}/audit", headers=headers()
    ).json()
    (evidence,) = [row for row in audit if row["event"] == "indoor_facility"]
    assert evidence["detail"] == {
        "model_decision": model_decision,
        "model_passage_ids": selected,
        "passage_ids": ["tms-access", "tms-closure"],
    }


@pytest.mark.parametrize(
    "question",
    [
        "How much does Wi-Fi cost at Sai Kung?",
        "Is there a fee for luggage storage at Sai Kung?",
        "Does the accessible toilet at Tai Mo Shan have Wi-Fi?",
        "How much is the accessible toilet at Tai Mo Shan?",
    ],
)
def test_unsupported_topic_has_no_evidence_or_draft(client, question):
    reply = client.post("/ask", json={"question": question}).json()
    assert reply["decision"] == "unknown"
    assert (
        reply["citations"] == reply["selected_passage_ids"] == reply["tools_used"] == []
    )
    assert reply["lookup"] is reply["proposal"] is None


@pytest.mark.parametrize(
    "question,passage,source",
    [
        ("What are Sai Kung’s weekly opening hours?", "sk-hours", "afcd-sk"),
        ("How do I get to Tai Mo Shan?", "tms-bus", "afcd-tms"),
    ],
)
def test_supported_guidance_keeps_its_source(client, question, passage, source):
    reply = client.post("/ask", json={"question": question}).json()
    assert reply["decision"] == "answer" and reply["selected_passage_ids"] == [passage]
    assert [c["source_id"] for c in reply["citations"]] == [source]
    assert reply["tools_used"] == [] and reply["proposal"] is None
