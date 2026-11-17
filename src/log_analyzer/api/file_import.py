"""Import bez buforowania całego pliku w Streamlit ani request.body()."""

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from log_analyzer.contracts import AnalysisImportResult, AnalysisSourceOptions, AnalyzeRequest, MAX_LOG_LINES
from log_analyzer.parsing.file_input import LogFileReader, LogImportError, MAX_FILE_BYTES


def build_file_import_router(analyze_and_save) -> APIRouter:
    router = APIRouter()

    @router.get("/import", response_class=HTMLResponse, include_in_schema=False)
    def import_page():
        page = Path(__file__).with_name("import.html").read_text(encoding="utf-8")
        dashboard_url = os.getenv("DASHBOARD_PUBLIC_URL", "http://localhost:8501").rstrip("/")
        page = page.replace("__DASHBOARD_URL__", json.dumps(dashboard_url).replace("<", "\\u003c"))
        page = page.replace("__MAX_BYTES__", str(MAX_FILE_BYTES)).replace("__MAX_LINES__", str(MAX_LOG_LINES))
        return HTMLResponse(page)

    @router.post("/api/v1/analyze/file", response_model=AnalysisImportResult, openapi_extra={
        "requestBody": {"required": True, "content": {"application/octet-stream": {
            "schema": {"type": "string", "format": "binary"}}}},
    })
    async def analyze_file(
        request: Request,
        log_format: Literal["hdfs", "ssh"] = "hdfs",
        source_timezone: str | None = Query(default=None, max_length=100),
        source_year: int | None = Query(default=None, ge=1900, le=2100),
        data_scope: Literal["unknown", "sample", "complete"] = "unknown",
    ):
        reader = LogFileReader()
        try:
            options = AnalysisSourceOptions(log_format=log_format, source_timezone=source_timezone,
                                            source_year=source_year, data_scope=data_scope)
            if declared_size := request.headers.get("content-length"):
                try:
                    size = int(declared_size)
                    if size < 0:
                        raise ValueError
                except ValueError as error:
                    raise HTTPException(422, "Niepoprawna długość przesyłanego pliku.") from error
                reader.check_size(size)
            async for chunk in request.stream():
                reader.feed(chunk)
            payload = AnalyzeRequest(logs=reader.finish(), **options.model_dump())
        except LogImportError as error:
            raise HTTPException(error.status_code, str(error)) from error
        except ValidationError as error:
            raise HTTPException(422, "Sprawdź format, strefę czasową i rok źródła.") from error
        # Parser, reguły i SQLite działają poza pętlą odbioru HTTP.
        result = await run_in_threadpool(analyze_and_save, payload)
        return AnalysisImportResult(analysis_id=result.analysis_id, event_count=len(result.events),
                                    finding_count=len(result.findings))

    return router
