import json
from datetime import date
from pathlib import Path

from .types import Area, Citation, Lookup, Status

DATA = Path(__file__).resolve().parents[1] / "data"


def read(name):
    return json.loads((DATA / name).read_text())


SNAPSHOT = read("snapshot.json")
CALENDAR = read("calendar.json")
PASSAGES = {p["id"]: p for p in read("passages.json")}
DAY = date.fromisoformat(SNAPSHOT["snapshot_date"])
SOURCES = SNAPSHOT["sources"]


def citations(pairs):
    locations = {}
    for source, section in pairs:
        sections = locations.setdefault(source, [])
        if section not in sections:
            sections.append(section)
    return [
        Citation(source_id=sid, locators=sections, **SOURCES[sid])
        for sid, sections in locations.items()
    ]


def fact_citations(facts):
    return citations((p["source_id"], p["locator"]) for p in facts)


def lookup(args: Lookup, *, notices=None) -> Status:
    centre, area, day = args.centre, args.area, args.local_date
    key = day.isoformat()
    hours = None
    timetable = SNAPSHOT["schedule"]
    rule = PASSAGES[timetable["rules"][centre]]
    refs = [(rule["source_id"], rule["locator"])]
    subject = (
        centre.title
        if area == Area.CENTRE
        else f"{centre.title}'s Hiking Etiquette photo exhibition"
    )
    applicable = []
    if not SNAPSHOT["calendar_range"][0] <= key <= SNAPSHOT["calendar_range"][1]:
        refs.append(
            ("hk-1823-index", "Published dataset coverage / supported local subset")
        )
        status, basis = "unknown", "outside_calendar"
        first, last = SNAPSHOT["calendar_range"]
        message = f"{key} is outside the supported calendar of {first} through {last}."
    else:
        year = CALENDAR[str(day.year)]
        holiday = year["holidays"].get(key)
        lunar = key in year["lunar_new_year_days"]
        refs.append((year["lunar_source"], f"Gregorian date {key}"))
        event_locator = (
            f"VEVENT DTSTART {day:%Y%m%d}"
            if holiday
            else f"No dated holiday entry for {key}"
        )
        refs.append((year["holiday_source"], event_locator))
        if area == Area.PHOTO:
            refs.append(("afcd-photo", "Hiking Etiquette / Date & Location"))
        if lunar:
            status, basis = "scheduled_closed", "lunar_days_1_2"
            message = f"{subject} is scheduled to close on lunar new year day {year['lunar_new_year_days'].index(key) + 1}."
        elif area == Area.PHOTO:
            listed = day.weekday() >= 5 or bool(holiday)
            status, basis = (
                ("published_session", "exhibition_schedule")
                if listed
                else ("scheduled_closed", "no_exhibition_session")
            )
            message = (
                f"{subject} has a published session without stated times."
                if listed
                else f"No {subject} session is listed for this weekday."
            )
        elif day.weekday() == timetable["closed_weekday"] and not holiday:
            status, basis = "scheduled_closed", "ordinary_tuesday"
            message = f"{subject} is scheduled to close on this Tuesday."
        else:
            hours = timetable["hours"]
            status, basis = (
                "published_hours",
                "public_holiday" if holiday else "regular_hours",
            )
            when = f" ({holiday})" if holiday else ""
            message = f"{subject}'s published hours for {key}{when} are {hours}."
        # A page revision or the retrieval time cannot supply a missing effective date.
        uncertain_history = []
        for n in SNAPSHOT["notices"] if notices is None else notices:
            if n["centre"] != centre or n["area"] not in (Area.CENTRE, area):
                continue
            if n["from"] and key < n["from"] or n["to"] and key > n["to"]:
                continue
            if not n["from"] and key < n["observed_on"]:
                uncertain_history.append(n)
                continue
            applicable.append(n)
            refs.extend((s, n["description"]) for s in [n["source_id"], *n["also"]])
        if applicable:
            # A centre closure covers its indoor activities. A programme notice never closes the centre.
            known = [n for n in applicable if n["to"] or key <= n["observed_on"]]
            candidates = (
                [n for n in known if n["kind"] == "closure"] or known or applicable
            )
            decisive = next(
                (
                    n
                    for n in candidates
                    if n["kind"] == "closure" and n["area"] == Area.CENTRE
                ),
                candidates[0],
            )
            detail = decisive["description"]
            recorded = decisive["observed_on"]
            if not decisive["to"] and key > recorded:
                status, basis = "unknown", "after_notice_observation"
                message = f"{detail} The snapshot recorded this on {recorded} with no end date. The status on {key} is unconfirmed."
            elif decisive["kind"] == "reopening":
                status, basis = "reopening_observed", "snapshot_reopening"
                message = f"{detail} AFCD reported reopening as of {recorded}. The effective reopening date is unspecified."
            else:
                status, basis = "notice_closed", "closure_notice"
                start = (
                    f" Effective from {decisive['from']}."
                    if decisive["from"]
                    else " The start date is unspecified."
                )
                end = (
                    f" The last covered date is {decisive['to']}."
                    if decisive["to"]
                    else " No reopening date was published."
                )
                message = (
                    f"{detail} A closure was recorded as of {recorded}.{start}{end}"
                )
            for notice in applicable:
                if notice is not decisive:
                    message += f" {notice['description']}"
        elif uncertain_history:
            status, basis = "unknown", "undated_notice_history"
            message = f"{subject} has a later notice with no effective date. Its status on {key} is unknown."
            for n in uncertain_history:
                refs.append((n["source_id"], n["description"]))
        else:
            message += " Actual opening on the day is unconfirmed."
    refs_out = citations(refs)
    return Status(
        centre=centre,
        area=area,
        local_date=day,
        status=status,
        basis=basis,
        message=message,
        published_hours=hours,
        snapshot_date=DAY,
        notices=applicable,
        source_ids=[c.source_id for c in refs_out],
        citations=refs_out,
    )
