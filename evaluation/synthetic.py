"""Invented notices used only in the three labelled rule checks."""

from unittest.mock import patch

from app.snapshot import SOURCES, lookup
from app.types import Lookup

NOTICES = {
    "bounded_photo": {
        "kind": "closure",
        "source_id": "fixture-scoped",
        "from": "2026-11-28",
        "to": "2026-11-28",
        "description": "Synthetic one-day suspension of the photo exhibition.",
    },
    "undated_reopening": {
        "kind": "reopening",
        "source_id": "fixture-reopening",
        "from": None,
        "to": None,
        "description": "Synthetic reopening of the photo exhibition.",
    },
}


def simulated(case, *, additional_notices=()):
    notice = {
        **NOTICES[case["fixture"]],
        "centre": "sai-kung",
        "area": "photo-exhibition",
        "observed_on": "2026-11-26",
        "also": [],
    }
    sid = notice["source_id"]
    metadata = {
        "title": "Synthetic rule fixture",
        "url": "urn:fixture:" + sid,
        "scope": "Photo exhibition only",
        "retrieved_at": "2026-11-26T00:00:00+08:00",
    }
    with patch.dict(SOURCES, {sid: metadata}):
        args = Lookup(centre=case["centre"], area=case["area"], local_date=case["date"])
        return lookup(args, notices=[*additional_notices, notice])
