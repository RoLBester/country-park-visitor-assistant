from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .search import embedding
from .snapshot import PASSAGES, SOURCES
from .types import Proposal


def connect():
    return psycopg.connect(row_factory=dict_row)


def initialize():
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(72981643)")
        db.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        db.execute(Path(__file__).with_name("schema.sql").read_text())
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO sources VALUES (%s,%s) ON CONFLICT (id)
                DO UPDATE SET metadata=EXCLUDED.metadata""",
                [(key, Jsonb(val)) for key, val in SOURCES.items()],
            )
            rows = [
                (
                    p["id"],
                    p["source_id"],
                    p["centre"],
                    p["locator"],
                    p["text"],
                    p["keywords"],
                    embedding(p["text"] + " " + p["keywords"]),
                )
                for p in PASSAGES.values()
            ]
            cur.executemany(
                """INSERT INTO passages VALUES (%s,%s,%s,%s,%s,%s,%s::vector)
                ON CONFLICT (id) DO UPDATE SET source_id=EXCLUDED.source_id, centre=EXCLUDED.centre,
                locator=EXCLUDED.locator, text=EXCLUDED.text, keywords=EXCLUDED.keywords,
                embedding=EXCLUDED.embedding""",
                rows,
            )
        db.execute("DELETE FROM passages WHERE NOT (id = ANY(%s))", (list(PASSAGES),))


def event(db, rid, name, sources, detail, actor="assistant", pid=None):
    db.execute(
        """INSERT INTO audit(request_id,proposal_id,event,actor,source_ids,detail)
                  VALUES (%s,%s,%s,%s,%s,%s)""",
        (rid, pid, name, actor, sources, Jsonb(detail)),
    )


def save_request(reply, draft, trace):
    with connect() as db:
        rid = reply.request_id
        db.execute("INSERT INTO requests(id) VALUES (%s)", (rid,))
        for name, refs, detail in trace:
            event(db, rid, name, refs, detail)
        if draft:
            row = db.execute(
                """INSERT INTO proposals(id,request_id,centre,reason,source_ids)
                VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                (uuid4(), rid, draft.centre, draft.reason, draft.source_ids),
            ).fetchone()
            reply.proposal = Proposal(**row)
            event(
                db,
                rid,
                "proposal_staged",
                draft.source_ids,
                {"state": "pending", "tool": "propose_followup"},
                pid=row["id"],
            )
        event(
            db,
            rid,
            "reply",
            [c.source_id for c in reply.citations],
            {
                "decision": reply.decision,
                "passage_ids": reply.selected_passage_ids,
                "tools_used": reply.tools_used,
            },
        )
    return reply


def decide(pid, decision, reviewer):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM proposals WHERE id=%s FOR UPDATE", (pid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Proposal not found.")
        target = "approved" if decision == "approve" else "rejected"
        if row["state"] not in ("pending", target):
            raise HTTPException(409, f"The proposal has already been {row['state']}.")
        if row["state"] == "pending":
            db.execute(
                "INSERT INTO reviews(proposal_id, reviewer, decision) VALUES (%s,%s,%s)",
                (pid, reviewer, decision),
            )
            db.execute("UPDATE proposals SET state=%s WHERE id=%s", (target, pid))
            detail = {"from": "pending", "state": target, "decision": decision}
            event(
                db,
                row["request_id"],
                "review_decided",
                row["source_ids"],
                detail,
                reviewer,
                pid,
            )
            if decision == "approve":
                fid = uuid4()
                db.execute(
                    "INSERT INTO followups(id,proposal_id) VALUES (%s,%s)", (fid, pid)
                )
                event(
                    db,
                    row["request_id"],
                    "followup_created",
                    row["source_ids"],
                    {"followup_id": str(fid), "state": target, "decision": decision},
                    reviewer,
                    pid,
                )
        return db.execute(
            """SELECT p.id AS proposal_id,p.request_id,p.centre,p.reason,p.source_ids,p.state,
                      r.reviewer,r.decision,r.decided_at,f.id AS followup_id,f.created_at AS followup_created_at
               FROM proposals p JOIN reviews r ON r.proposal_id=p.id
               LEFT JOIN followups f ON f.proposal_id=p.id WHERE p.id=%s""",
            (pid,),
        ).fetchone()
