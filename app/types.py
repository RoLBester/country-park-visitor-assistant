from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("local_date", mode="before", check_fields=False)
    @classmethod
    def plain_calendar_date(cls, value):
        if value is None or type(value) is date:
            return value
        if (
            not isinstance(value, str)
            or len(value) != 10
            or value[4:5] != "-"
            or value[7:8] != "-"
        ):
            raise ValueError("Use a Hong Kong date in YYYY-MM-DD format.")
        return date.fromisoformat(value)


class Centre(StrEnum):
    SAI = "sai-kung"
    SHING = "shing-mun"
    TAI = "tai-mo-shan"

    @property
    def title(self):
        return self.value.replace("-", " ").title()


class Area(StrEnum):
    CENTRE = "centre"
    PHOTO = "photo-exhibition"


Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)
]


class Question(Input):
    question: Text = Field(examples=["What can I borrow at Shing Mun?"])
    centre: Centre | None = None
    local_date: date | None = None
    area: Area | None = None


class Lookup(Input):
    centre: Centre
    local_date: date
    area: Area = Area.CENTRE

    @model_validator(mode="after")
    def supported_area(self):
        if self.area == Area.PHOTO and self.centre == Centre.SHING:
            raise ValueError(
                "The photo exhibition is listed at Sai Kung and Tai Mo Shan."
            )
        return self


class DraftTool(Input):
    centre: Centre
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=240)
    ]
    source_ids: list[str] = Field(min_length=1, max_length=8)


class Selection(Input):
    decision: Literal["answer", "unknown", "clarify"]
    passage_ids: list[str] = Field(default_factory=list, max_length=3)


class Review(Input):
    decision: Literal["approve", "reject"]


class Citation(BaseModel):
    source_id: str
    title: str
    url: str
    retrieved_at: str
    scope: str
    locators: list[str]


class Status(BaseModel):
    centre: Centre
    local_date: date
    area: Area
    status: Literal[
        "published_hours",
        "published_session",
        "scheduled_closed",
        "notice_closed",
        "reopening_observed",
        "unknown",
    ]
    published_hours: str | None
    basis: str
    message: str
    snapshot_date: date
    source_ids: list[str]
    notices: list[dict]
    citations: list[Citation]
    timezone: str = "Asia/Hong_Kong"


class Proposal(BaseModel):
    id: UUID
    request_id: UUID
    centre: Centre
    reason: str
    source_ids: list[str]
    state: Literal["pending", "approved", "rejected"]


class Reply(BaseModel):
    request_id: UUID
    decision: Literal["answer", "status", "unknown", "clarify", "proposal"]
    answer: str
    citations: list[Citation]
    retrieved_passage_ids: list[str]
    selected_passage_ids: list[str]
    tools_used: list[str]
    snapshot_date: date
    lookup: Status | None = None
    proposal: Proposal | None = None
