"""Kontrakty pierwszej wersji API JB. Wynik ML pozostaje osobnym etapem."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LogLine = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logs: list[LogLine] = Field(min_length=1, max_length=1000)
    log_format: Literal["hdfs", "ssh"] = "hdfs"


class NormalizedEvent(BaseModel):
    event_id: str
    raw: str
    timestamp: str | None = None
    timestamp_raw: str | None = None
    host: str | None = None
    component: str
    message: str
    template: str
    template_id: int
    block_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)


class EventGroup(BaseModel):
    group_id: str
    event_ids: list[str]


class AnalysisResponse(BaseModel):
    analysis_id: str
    events: list[NormalizedEvent]
    groups: list[EventGroup]
    detection_status: Literal["not_configured"] = "not_configured"
    reporting_status: Literal["not_run"] = "not_run"
    warnings: list[str]
