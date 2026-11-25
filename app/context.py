import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .types import Area, Centre, Question

HK = ZoneInfo("Asia/Hong_Kong")
ISO = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
RELATIVE = {"now": 0, "today": 0, "tomorrow": 1, "yesterday": -1}
WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
FOLLOW = (
    r"\b(?:please |can you |could you |would you )?ask (?:the )?staff\b|"
    r"\b(?:request|want|need|like|create|stage|propose|arrange) (?:a |one |a staff )?(?:staff )?follow[ -]?up\b|"
    r"\b(?:please |can you |could you |would you )follow[ -]?up\b|^follow[ -]?up\b|\brequest (?:a )?(?:staff )?review\b"
)


@dataclass
class Context:
    centre: Centre | None
    day: date | None
    area: Area
    timed: bool
    follow: bool
    no_follow: bool
    clarify: str | None


def resolve(q: Question, now: datetime | None = None):
    text = q.question.lower()
    names = {
        c
        for c in Centre
        if re.search(r"\b" + c.value.replace("-", "[- ]+") + r"\b", text)
    }
    if q.centre:
        names.add(q.centre)
    centre = next(iter(names)) if len(names) == 1 else None
    issue = (
        "Which single centre should I check (Sai Kung, Shing Mun or Tai Mo Shan)?"
        if len(names) > 1
        else None
    )
    photo = bool(
        re.search(r"hiking etiquette|photo(?:graphy)? exhibit|photo show", text)
    )
    area = q.area or (Area.PHOTO if photo else Area.CENTRE)
    if photo and q.area == Area.CENTRE:
        issue = "Do you mean the whole centre or the Hiking Etiquette photo exhibition?"
    if area == Area.PHOTO and centre == Centre.SHING:
        issue = "The listed photo exhibition venues include Sai Kung and Tai Mo Shan. Which do you mean?"
    days = {q.local_date} if q.local_date else set()
    today = (now or datetime.now(HK)).astimezone(HK).date()
    for word, offset in RELATIVE.items():
        if re.search(r"\b" + word + r"\b", text):
            days.add(today + timedelta(days=offset))
    literals = ISO.findall(text)
    try:
        days.update(date.fromisoformat(value) for value in literals)
        for value in re.findall(
            rf"\b\d{{1,2}} {MONTH} \d{{4}}\b|\b{MONTH} \d{{1,2}},? \d{{4}}\b", text
        ):
            for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
                try:
                    days.add(datetime.strptime(value.replace(",", ""), fmt).date())
                    break
                except ValueError:
                    continue
            else:
                raise ValueError
    except ValueError:
        issue = "Please give a valid Hong Kong calendar date in YYYY-MM-DD format."
    if len(days) > 1:
        issue = "Which single Hong Kong date should I check?"
    day = next(iter(days)) if len(days) == 1 else None
    no_follow = bool(
        re.search(
            r"(?:do not|don't|without|no|never)\s+(?:(?:create|stage|request|propose|a|any|staff)\s+)*(?:follow[ -]?up|ask(?:ing)? (?:the )?staff|review)\b",
            text,
        )
    )
    follow = bool(re.search(FOLLOW, text)) and not no_follow
    usual = bool(
        re.search(
            r"\b(usual|regular|normally|normal|weekly|typically|typical|published hours|opening hours|timetable)\b",
            text,
        )
    )
    when = bool(
        re.search(
            rf"\b(?:on (?:a |the )?{WEEKDAY}|next |this (?:week|{WEEKDAY})|today|tomorrow|yesterday|now)\b",
            text,
        )
    )
    status_words = bool(
        re.search(
            r"\b(open|opens|opening|hours|timetable|close|closes|closed|closure|shut|status|visit|visiting|session|running|held|go)\b",
            text,
        )
    )
    timed = (status_words and (bool(days) or bool(literals) or when)) or bool(
        re.search(
            r"\b(is|will|was|can|are|could)\b.*\b(open|closed|visit|running|held)\b|\b(status|open on|closed on)\b",
            text,
        )
    )
    if (
        usual or follow or re.search(r"\b(fee|admission|free|ticket)\b", text)
    ) and not (days or when):
        timed = False
    if timed and not day and not issue:
        issue = (
            "Which Hong Kong date should I check? Use YYYY-MM-DD, today or tomorrow."
        )
    if (timed or follow or usual) and not centre and not issue:
        issue = "Which centre do you mean (Sai Kung, Shing Mun or Tai Mo Shan)?"
    return Context(centre, day, area, timed, follow, no_follow, issue)
