import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from uuid import uuid4

from psycopg import sql

from app import db


@contextmanager
def isolated_schema():
    """Give every API connection in this process a fresh search path for a check run."""
    name = "park_check_" + uuid4().hex
    previous = os.environ.get("PGOPTIONS")
    with db.connect() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        os.environ["PGOPTIONS"] = f"-c search_path={name},public"
        yield
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous
        with db.connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def headers(role="reviewer"):
    return {"Authorization": "Bearer " + os.environ[role.upper() + "_TOKEN"]}


def check_approval(client, case, reply):
    assert reply["decision"] == "proposal" and reply["tools_used"] == [
        "propose_followup"
    ]
    p = reply["proposal"]
    assert (
        p["state"] == "pending" and p["centre"] == "shing-mun" and p["reason"].strip()
    )
    assert set(case["sources"]) <= set(p["source_ids"])
    pid, rid = p["id"], reply["request_id"]
    path = f"/review/proposals/{pid}/decision"
    request_audit = f"/review/requests/{rid}/audit"
    assert pid in [
        r["id"] for r in client.get("/review/proposals", headers=headers()).json()
    ]
    with db.connect() as sql_db:
        assert not sql_db.execute(
            "SELECT id FROM followups WHERE proposal_id=%s", (pid,)
        ).fetchone()
    scenario = case["scenario"]

    def decide(decision, access=None):
        return client.post(
            path,
            json={"decision": decision},
            headers=headers() if access is None else access,
        )

    codes, decisions = [], []
    if scenario == "visitor":
        codes = [
            decide("approve", headers("visitor")).status_code,
            client.get(request_audit, headers=headers("visitor")).status_code,
        ]
        assert codes == [403, 403]
    elif scenario == "identity":
        codes = [
            decide("approve", {}).status_code,
            decide(
                "approve", {"Authorization": "Bearer invalid", "X-Role": "reviewer"}
            ).status_code,
        ]
        assert codes == [401, 401]
    elif scenario == "concurrent":
        barrier = Barrier(6)

        def together(_):
            barrier.wait(timeout=15)
            return decide("approve")

        with ThreadPoolExecutor(6) as pool:
            responses = list(pool.map(together, range(6)))
        codes = [r.status_code for r in responses]
        assert codes == [200] * 6
        decisions = [r.json() for r in responses]
        assert all(d == decisions[0] for d in decisions)
    else:
        sequences = {
            "stage": [],
            "approve": ["approve"],
            "reject": ["reject"],
            "repeat": ["approve", "approve"],
            "reject_then_approve": ["reject", "approve"],
            "approve_then_reject": ["approve", "reject"],
        }
        responses = [decide(d) for d in sequences[scenario]]
        codes = [r.status_code for r in responses]
        assert codes == ([200, 409] if "then" in scenario else [200] * len(responses))
        decisions = [r.json() for r in responses if r.status_code == 200]
        if scenario == "repeat":
            assert decisions[0] == decisions[1]
    with db.connect() as sql_db:
        stored = sql_db.execute(
            "SELECT * FROM proposals WHERE id=%s", (pid,)
        ).fetchone()
        reviews = sql_db.execute(
            "SELECT * FROM reviews WHERE proposal_id=%s", (pid,)
        ).fetchall()
        followups = sql_db.execute(
            "SELECT * FROM followups WHERE proposal_id=%s", (pid,)
        ).fetchall()
        audit = sql_db.execute(
            "SELECT * FROM audit WHERE request_id=%s ORDER BY seq", (rid,)
        ).fetchall()
    state = case["state"]
    assert stored["state"] == state and stored["source_ids"] == p["source_ids"]
    assert len(reviews) == int(state != "pending") and len(followups) == int(
        state == "approved"
    )
    if decisions:
        assert decisions[0]["followup_id"] == (
            str(followups[0]["id"]) if followups else None
        )
    events = [e["event"] for e in audit]
    expected = ["retrieved", "proposal_staged", "reply"]
    if state != "pending":
        expected.append("review_decided")
        assert reviews[0]["reviewer"] == os.environ["REVIEWER_ID"]
        assert reviews[0]["decision"] == (
            "approve" if state == "approved" else "reject"
        )
        entry = next(e for e in audit if e["event"] == "review_decided")
        assert (
            entry["actor"] == reviews[0]["reviewer"]
            and entry["detail"]["state"] == state
        )
        assert (
            entry["source_ids"] == stored["source_ids"]
            and entry["detail"]["decision"] == reviews[0]["decision"]
        )
    if state == "approved":
        expected.append("followup_created")
    assert events == expected and all(e["at"].tzinfo and e["source_ids"] for e in audit)
    assert audit[1]["detail"]["state"] == "pending"
    assert [
        e["event"] for e in client.get(request_audit, headers=headers()).json()
    ] == events
    return {
        "state": state,
        "responses": codes,
        "review_rows": len(reviews),
        "followup_rows": len(followups),
        "events": events,
    }
