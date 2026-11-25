"""Score the labelled visitor and approval cases against the selected actual API adapter."""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from urllib.request import urlopen

from fastapi.testclient import TestClient
from psycopg import Error as DatabaseError

from app import db
from app.api import create_app
from app.context import HK
from app.model import Fixture, Ollama
from app.snapshot import DAY, PASSAGES

from .support import check_approval, headers, isolated_schema

CASES = json.loads(Path(__file__).with_name("cases.json").read_text())
# Check the substance against independently transcribed details as well as the returned IDs.
DETAILS = {
    "A01": ["free"],
    "A02": ["map", "poles", "power bank"],
    "A03": ["toilet", "kiosk"],
    "A04": ["51", "Nina Tower"],
    "A05": ["2498 9326"],
    "A06": ["82", "Pineapple Dam"],
    "A07": ["paperbark", "relics"],
    "A08": ["stopped printing"],
    "A09": ["09:30–16:30", "Tuesdays"],
    "A10": ["09:30–16:30", "1 July 2026", "no reopening date"],
    "A11": ["before opening", "during service"],
    "A12": ["maintained footpaths"],
}


def exercise(client, case):
    response = client.post("/ask", json={"question": case["question"]})
    assert response.status_code == 200, f"HTTP {response.status_code}"
    reply = response.json()
    sources = [r["source_id"] for r in reply["citations"]]
    actual = {
        "decision": reply["decision"],
        "answer": reply["answer"],
        "source_ids": sources,
        "passage_ids": reply["selected_passage_ids"],
        "tools": reply["tools_used"],
    }
    status = reply["lookup"]
    if status:
        actual.update(
            status=status["status"],
            basis=status["basis"],
            area=status["area"],
            centre=status["centre"],
            local_date=status["local_date"],
            proposal=bool(reply["proposal"]),
        )
    try:
        if case["group"] == "approval":
            actual.update(check_approval(client, case, reply))
        else:
            assert reply["decision"] == case["decision"], "decision"
            assert set(case["sources"]) <= set(sources), "supporting source"
            assert all(
                r["url"].startswith("https://") and r["locators"]
                for r in reply["citations"]
            )
            if case["group"] == "guidance":
                assert set(case["passages"]) == set(reply["selected_passage_ids"]), (
                    "specific supporting passages"
                )
                assert set(reply["selected_passage_ids"]) <= set(
                    reply["retrieved_passage_ids"]
                )
                assert all(
                    PASSAGES[i]["source_id"] in sources for i in case["passages"]
                )
                assert all(
                    s.lower() in reply["answer"].lower() for s in DETAILS[case["id"]]
                ), "answer content"
                assert reply["tools_used"] == []
            if case["group"] == "lookup":
                expected_tools = ["lookup_status"] + (
                    ["propose_followup"] if case["proposal"] else []
                )
                assert reply["tools_used"] == expected_tools, "tool selection"
                assert status and (
                    status["centre"],
                    status["local_date"],
                    status["area"],
                ) == (case["centre"], case["date"], case["area"]), "lookup arguments"
                assert (status["status"], status["basis"]) == (
                    case["status"],
                    case["basis"],
                ), "status or calendar rule"
                assert bool(reply["proposal"]) == case["proposal"], "draft outcome"
                assert set(case.get("notice_areas", [])) <= {
                    n["area"] for n in status["notices"]
                }
                if status["status"] == "published_hours":
                    assert status["published_hours"] == "09:30–16:30"
                log = client.get(
                    f"/review/requests/{reply['request_id']}/audit", headers=headers()
                ).json()
                recorded = next(e for e in log if e["event"] == "lookup_status")
                assert (
                    recorded["detail"]["status"] == case["status"]
                    and recorded["source_ids"] == sources
                )
            if case["group"] == "boundaries":
                assert (
                    not reply["tools_used"]
                    and not reply["proposal"]
                    and not reply["selected_passage_ids"]
                )
    except (AssertionError, KeyError, TypeError, StopIteration) as exc:
        return {
            "passed": False,
            "error": str(exc) or "Observed records differed from the label.",
            "observed": actual,
        }
    return {"passed": True, "observed": actual}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--adapter", choices=["fixture", "ollama"], required=True)
    args = cli.parse_args()
    model = Fixture() if args.adapter == "fixture" else Ollama()
    runtime = {
        "adapter": args.adapter,
        "python": sys.version.split()[0],
        "fastapi": version("fastapi"),
    }
    if args.adapter == "ollama":
        host = os.environ["OLLAMA_HOST"].rstrip("/")
        runtime.update(
            model=model.model,
            server=json.load(urlopen(host + "/api/version", timeout=8))["version"],
            client=version("ollama"),
        )
        models = json.load(urlopen(host + "/api/tags", timeout=8))["models"]
        runtime["model_digest"] = next(
            m["digest"] for m in models if m["name"] == model.model
        )
    records = []
    with isolated_schema(), TestClient(create_app(model)) as client:
        with db.connect() as conn:
            runtime.update(
                conn.execute("""SELECT current_setting('server_version') AS postgres,
                (SELECT extversion FROM pg_extension WHERE extname='vector') AS pgvector""").fetchone()
            )
        for case in CASES:
            if case["group"] == "synthetic":
                continue
            try:
                result = exercise(client, case)
            except (AssertionError, DatabaseError, RuntimeError, ValueError) as error:
                result = {"passed": False, "error": f"{type(error).__name__}: {error}"}
            records.append({"id": case["id"], "group": case["group"], **result})
            print(
                f"{case['id']} {'pass' if result['passed'] else 'FAIL'}",
                file=sys.stderr,
                flush=True,
            )
    totals = defaultdict(lambda: {"passed": 0, "total": 0})
    for row in records:
        totals[row["group"]]["total"] += 1
        totals[row["group"]]["passed"] += int(row["passed"])
    print(
        json.dumps(
            {
                "finished_at": datetime.now(HK).isoformat(timespec="seconds"),
                "snapshot": DAY.isoformat(),
                "runtime": runtime,
                "scores": dict(totals),
                "cases": records,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return int(any(not r["passed"] for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
