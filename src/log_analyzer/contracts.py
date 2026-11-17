"""Wspólne kontrakty API, raportowania i dashboardu."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

LogLine = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
MAX_LOG_LINES = 5000


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logs: list[LogLine] = Field(min_length=1, max_length=MAX_LOG_LINES)
    log_format: Literal["hdfs", "ssh"] = "hdfs"
    source_timezone: str | None = Field(default=None, max_length=100)
    source_year: int | None = Field(default=None, ge=1900, le=2100)
    data_scope: Literal["unknown", "sample", "complete"] = "unknown"

    @field_validator("source_timezone")
    @classmethod
    def validate_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError("Podaj poprawną strefę źródła, np. Europe/Warsaw lub UTC.") from error
        return value


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
    source_line: int | None = None
    log_level: str | None = None
    event_type: str = "other"
    timestamp_local: str | None = None
    timezone_source: Literal["log", "configuration", "unknown"] = "unknown"
    time_issue: str | None = None


class EventGroup(BaseModel):
    group_id: str
    event_ids: list[str]
    ml_prediction: Literal["normal", "anomaly"] | None = None
    ml_score: float | None = Field(default=None, ge=0, le=1)
    model_version: str | None = None


class RuleDefinition(BaseModel):
    rule_id: str
    version: str
    name: str
    description: str


class Finding(BaseModel):
    finding_id: str
    analysis_id: str
    rule_ids: list[str]
    title: str
    reason: str
    source: Literal["rules", "ml", "both"] = "rules"
    priority: Literal["unassessed", "low", "medium", "high", "critical"] = "unassessed"
    priority_is_provisional: bool = True
    event_ids: list[str] = Field(min_length=1)
    node: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    time_basis: Literal["utc", "source_local", "unknown"] = "unknown"
    score: float | None = Field(default=None, ge=0, le=1)
    model_version: str | None = None
    rules_version: str = "hdfs-rules-v1"
    details: dict[str, str | int] = Field(default_factory=dict)
    rule_definitions: list[RuleDefinition] = Field(default_factory=list)


class FindingHistory(BaseModel):
    findings: list[Finding]
    total: int
    limit: int
    offset: int


class AnalysisResponse(BaseModel):
    analysis_id: str
    log_format: Literal["hdfs", "ssh"] = "hdfs"
    events: list[NormalizedEvent]
    groups: list[EventGroup]
    detection_status: Literal["not_configured", "completed", "partial"] = "not_configured"
    reporting_status: Literal["not_run"] = "not_run"
    warnings: list[str]
    diagnostics: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    rules_status: Literal["completed", "unsupported", "not_run"] = "not_run"
    processing_status: Literal["completed"] = "completed"
    source_timezone: str | None = None
    source_year: int | None = None
    data_scope: Literal["unknown", "sample", "complete"] = "unknown"


class GenerateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str | None = Field(default=None, min_length=1, max_length=512)
    finding_id: UUID | None = None

    @model_validator(mode="after")
    def one_report_source(self):
        if (self.group_id is None) == (self.finding_id is None):
            raise ValueError("Wybierz dokładnie jedną grupę lub jedno wykrycie do raportowania.")
        return self


class TrescRaportu(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    podsumowanie: str = Field(min_length=1)
    kluczowe_zdarzenia: list[str] = Field(min_length=1)
    rekomendacja: str = Field(min_length=1)


class RaportZdarzen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    created_at: datetime
    event_ids: list[str] = Field(min_length=1)
    host: str | None
    liczba_zdarzen: int = Field(ge=1)
    liczba_zdarzen_bez_czasu: int = Field(ge=0)
    czas_od: datetime | None
    czas_do: datetime | None
    tresc: TrescRaportu
    analysis_id: str | None = None
    group_id: str | None = None
    generation_mode: Literal["manual"] = "manual"
    finding: Finding | None = None
    czas_zrodlowy_od: str | None = None
    czas_zrodlowy_do: str | None = None
    llm_input_mode: Literal["full", "aggregated"] = "full"
    llm_event_ids: list[str] = Field(default_factory=list)
    llm_omitted_events: int = Field(default=0, ge=0)


class ReportSummary(BaseModel):
    report_id: UUID
    created_at: datetime
    host: str | None
    # Starsze wpisy mogą zawierać tylko podstawowe metadane.
    liczba_zdarzen: int | None = Field(default=None, ge=1)
    podsumowanie: str = ""


class ReportHistory(BaseModel):
    reports: list[ReportSummary]
    total: int = Field(ge=0)
    known_hosts: list[str]
    known_host_count: int = Field(ge=0)
    latest_created_at: datetime | None
    limit: int
    offset: int


class DetectionMetrics(BaseModel):
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    accuracy: float | None = Field(default=None, ge=0, le=1)
    roc_auc: float | None = Field(default=None, ge=0, le=1)
    average_precision: float | None = Field(default=None, ge=0, le=1)
    per_class: dict[str, dict[str, float]] = Field(default_factory=dict)
    confusion_matrix: list[list[int]]
    n: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_matrix(self):
        matrix = self.confusion_matrix
        if len(matrix) != 2 or any(len(row) != 2 for row in matrix):
            raise ValueError("Macierz pomyłek musi mieć rozmiar 2 × 2, w kolejności klas [0, 1].")
        if any(value < 0 for row in matrix for value in row):
            raise ValueError("Macierz pomyłek nie może zawierać ujemnych wartości.")
        if sum(sum(row) for row in matrix) != self.n:
            raise ValueError("Liczba przykładów nie zgadza się z macierzą pomyłek.")
        return self


class ExperimentSplit(BaseModel):
    train: int = Field(ge=1)
    val: int = Field(default=0, ge=0)
    test: int = Field(default=0, ge=0)


class ExperimentResult(BaseModel):
    model: str = Field(min_length=1)
    date: date
    dataset: str = Field(default="Nie podano", min_length=1)
    data_source: Literal["synthetic", "loghub", "unknown"] = "unknown"
    class_labels: list[int] = Field(default_factory=lambda: [0, 1])
    split: ExperimentSplit
    validation: DetectionMetrics | None = None
    test: DetectionMetrics | None = None

    @model_validator(mode="after")
    def validate_experiment(self):
        if self.class_labels != [0, 1]:
            raise ValueError("Oczekiwana kolejność klas: 0 — normalne, 1 — anomalie.")
        if self.validation is None and self.test is None:
            raise ValueError("Eksperyment musi zawierać metryki walidacyjne albo testowe.")
        if self.validation and self.validation.n != self.split.val:
            raise ValueError("Rozmiar walidacji nie zgadza się z podziałem danych.")
        if self.test and self.test.n != self.split.test:
            raise ValueError("Rozmiar ocenianej części nie zgadza się z podziałem danych.")
        return self


class EvaluationResults(BaseModel):
    experiments: list[ExperimentResult] = Field(default_factory=list)
