"""Walk a synthetic request through the running local API and print the observed records."""

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    settings = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    port = os.environ.get("APP_PORT", settings.get("APP_PORT", "8765"))
    base = f"http://127.0.0.1:{port}"

    def call(path, body=None, review=False):
        headers = {"Content-Type": "application/json"}
        if review:
            headers["Authorization"] = "Bearer " + settings["REVIEWER_TOKEN"]
        req = Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urlopen(req, timeout=180) as response:
            return json.load(response)

    answer = call("/ask", {"question": "What can I borrow at Shing Mun?"})
    status = call("/status?centre=tai-mo-shan&local_date=2026-11-26")
    staged = call(
        "/ask",
        {
            "question": "Will Tai Mo Shan be open on 2027-01-02? Please ask staff to check."
        },
    )
    draft = staged["proposal"]
    assert answer["decision"] == "answer" and "afcd-sm" in {
        c["source_id"] for c in answer["citations"]
    }
    assert (
        status["status"] == "notice_closed" and staged["lookup"]["status"] == "unknown"
    )
    assert draft and draft["state"] == "pending"
    pending = call("/review/proposals?state=pending", review=True)
    assert draft["id"] in [p["id"] for p in pending]
    path = f"/review/proposals/{draft['id']}/decision"
    approved = call(path, {"decision": "approve"}, review=True)
    assert (
        approved["followup_id"]
        and call(path, {"decision": "approve"}, review=True) == approved
    )
    audit = call(f"/review/requests/{draft['request_id']}/audit", review=True)
    assert [r["event"] for r in audit] == [
        "retrieved",
        "lookup_status",
        "proposal_staged",
        "reply",
        "review_decided",
        "followup_created",
    ]
    print(
        json.dumps(
            {
                "model_adapter": call("/health")["model_adapter"],
                "snapshot": status["snapshot_date"],
                "visitor_answer": {
                    "text": answer["answer"],
                    "citations": answer["citations"],
                },
                "closure": {
                    "date": status["local_date"],
                    "status": status["status"],
                    "published_hours": status["published_hours"],
                    "text": status["message"],
                    "citations": status["citations"],
                },
                "requested_visit": {
                    "date": staged["lookup"]["local_date"],
                    "text": staged["answer"],
                },
                "pending_proposal": draft,
                "approved_followup": approved,
                "audit": audit,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
