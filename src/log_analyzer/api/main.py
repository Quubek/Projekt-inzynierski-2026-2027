"""Uruchomienie:  python -m uvicorn log_analyzer.api.main:app --app-dir src."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from httpx import RequestError, TimeoutException
from ollama import ResponseError
from pydantic import ValidationError

from log_analyzer.contracts import (
    AnalysisResponse, AnalyzeRequest, EvaluationResults, Finding, FindingHistory, GenerateReportRequest,
    RaportZdarzen, ReportHistory,
)
from log_analyzer.evaluation import load_evaluation_results
from log_analyzer.detection.model import model_is_available
from log_analyzer.pipeline import analyze
from log_analyzer.reporting import service as reporting_service
from log_analyzer.reporting.ollama_klient import EmptyModelOutputError
from log_analyzer.storage import sqlite_repo
from log_analyzer.api.file_import import build_file_import_router

app = FastAPI(title="Analiza logow - API JB", version="0.1.0")


@app.get("/health")
def health():
    model_path = os.getenv("DETECTION_MODEL_PATH")
    detection = "configured" if model_path and model_is_available(model_path) else "not_configured"
    return {"status": "ok", "detection": detection, "rules": "hdfs-rules-v1", "reporting": "manual"}


@app.get("/api/v1/evaluation", response_model=EvaluationResults)
def read_evaluation():
    try:
        return load_evaluation_results()
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=503, detail="Nie można odczytać wyników eksperymentów. Sprawdź plik wyników HD.",
        ) from error


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
def analyze_logs(request: AnalyzeRequest):
    try:
        result = analyze(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        sqlite_repo.zapisz_analize(result.model_dump_json())
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Nie można zapisać analizy.") from error
    return result


app.include_router(build_file_import_router(analyze_logs))


@app.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisResponse)
def read_analysis(analysis_id: UUID):
    try:
        saved = sqlite_repo.pobierz_analize(str(analysis_id))
        result = AnalysisResponse.model_validate_json(saved) if saved is not None else None
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="Nie można odczytać analizy.") from error
    if result is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono analizy. Prześlij logi ponownie.")
    return result


@app.get("/api/v1/findings", response_model=FindingHistory)
def list_findings(
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    analysis_id: UUID | None = None,
    priority: Literal["unassessed", "low", "medium", "high", "critical"] | None = None,
    rule_id: str | None = Query(default=None, max_length=40),
    query: str | None = Query(default=None, max_length=150),
):
    try:
        return FindingHistory.model_validate(sqlite_repo.pobierz_wykrycia(
            limit=limit, offset=offset, analysis_id=str(analysis_id) if analysis_id else None,
            priority=priority, rule_id=rule_id, query=query,
        ))
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="Nie można odczytać wykryć.") from error


@app.get("/api/v1/findings/{finding_id}", response_model=Finding)
def read_finding(finding_id: UUID):
    try:
        saved = sqlite_repo.pobierz_wykrycie(str(finding_id))
        result = Finding.model_validate_json(saved) if saved is not None else None
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="Nie można odczytać wykrycia.") from error
    if result is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono wykrycia.")
    return result


@app.post(
    "/api/v1/analyses/{analysis_id}/reports", response_model=RaportZdarzen, status_code=201,
)
def generate_report(analysis_id: UUID, request: GenerateReportRequest):
    analysis = read_analysis(analysis_id)
    try:
        if request.finding_id:
            return reporting_service.generate_finding_report(analysis, str(request.finding_id))
        return reporting_service.generate_group_report(analysis, request.group_id)
    except TimeoutException as error:
        raise HTTPException(status_code=504, detail="Przekroczono czas oczekiwania na Ollamę.") from error
    except (ConnectionError, RequestError, ResponseError) as error:
        raise HTTPException(
            status_code=503,
            detail="Nie można wygenerować raportu. Sprawdź Ollamę i model qwen3:4b-instruct.",
        ) from error
    except (ValidationError, EmptyModelOutputError) as error:
        raise HTTPException(status_code=502, detail="Ollama zwróciła raport niezgodny ze schematem.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Nie można zapisać raportu.") from error


@app.get("/api/v1/reports", response_model=ReportHistory)
def list_reports(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    host: str | None = Query(default=None, min_length=1, max_length=255),
    unknown_host: bool = False,
    report_id_query: str | None = Query(default=None, max_length=64),
    created_from: datetime | None = None,
    created_before: datetime | None = None,
):
    if host is not None and unknown_host:
        raise HTTPException(status_code=422, detail="Wybierz host lub filtr braku hosta.")
    if any(value is not None and value.tzinfo is None for value in (created_from, created_before)):
        raise HTTPException(status_code=422, detail="Daty muszą zawierać strefę czasową.")
    if created_from and created_before and created_from >= created_before:
        raise HTTPException(status_code=422, detail="Początek zakresu musi poprzedzać koniec.")
    try:
        return ReportHistory.model_validate(sqlite_repo.pobierz_historie_raportow(
            limit=limit, offset=offset, host=host, unknown_host=unknown_host,
            report_id_query=report_id_query.strip() if report_id_query else None,
            created_from=created_from.astimezone(timezone.utc).isoformat() if created_from else None,
            created_before=created_before.astimezone(timezone.utc).isoformat() if created_before else None,
        ))
    except (sqlite3.Error, ValueError, ValidationError) as error:
        raise HTTPException(status_code=503, detail="Nie można odczytać historii raportów.") from error


@app.get("/api/v1/reports/{report_id}")
def read_report(report_id: UUID):
    # Odczyt istniejących raportów przez moduł SQLite JF.
    if not sqlite_repo.SCIEZKA_BAZY.exists():
        raise HTTPException(status_code=404, detail="Nie znaleziono raportu.")
    try:
        report = sqlite_repo.pobierz_raport(str(report_id))
        data = json.loads(report) if report is not None else None
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="Nie można odczytać raportu.") from error
    if report is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono raportu.")
    return data
