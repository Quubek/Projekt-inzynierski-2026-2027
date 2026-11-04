"""Uruchomienie: python -m uvicorn log_analyzer.api.main:app --app-dir src."""

import json
from uuid import UUID

from fastapi import FastAPI, HTTPException

from log_analyzer.contracts import AnalysisResponse, AnalyzeRequest
from log_analyzer.pipeline import analyze
from log_analyzer.storage import sqlite_repo

app = FastAPI(title="Analiza logow - API JB", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "detection": "not_configured", "reporting": "not_connected"}


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
def analyze_logs(request: AnalyzeRequest):
    try:
        return analyze(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/reports/{report_id}")
def read_report(report_id: UUID):
    # Odczyt istniejących raportów przez moduł SQLite JF.
    if not sqlite_repo.SCIEZKA_BAZY.exists():
        raise HTTPException(status_code=404, detail="Nie znaleziono raportu.")
    report = sqlite_repo.pobierz_raport(str(report_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono raportu.")
    return json.loads(report)
