"""Dashboard pobiera dane przez HTTP; nie otwiera bazy SQLite."""

import httpx
from pydantic import ValidationError

from log_analyzer.contracts import (
    AnalysisResponse, AnalyzeRequest, EvaluationResults, Finding, FindingHistory, RaportZdarzen, ReportHistory,
)


class ReportsApiError(Exception):
    """Komunikat, który można wyświetlić użytkownikowi dashboardu."""


class ReportsApi:
    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=10.0, transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def _request(
        self, method: str, path: str, *, params: dict | None = None,
        payload: dict | None = None, timeout: float | None = None,
    ):
        try:
            response = self.client.request(
                method, path, params=params, json=payload,
                timeout=timeout if timeout is not None else (30.0 if method == "POST" else 10.0),
            )
            if response.status_code == 404:
                message = (
                    "Nie znaleziono wykrycia. Odśwież listę."
                    if "/findings/" in path else
                    "Nie znaleziono zapisanej analizy. Prześlij logi ponownie."
                    if "/analyses/" in path else
                    "API nie udostępnia analizy logów. Sprawdź wersję uruchomionej aplikacji."
                    if method == "POST" else "Nie znaleziono raportu. Odśwież historię."
                )
                raise ReportsApiError(message)
            if response.status_code == 422:
                if method == "POST":
                    body = response.json()
                    detail = body.get("detail") if isinstance(body, dict) else None
                    if isinstance(detail, str):
                        raise ReportsApiError(f"Nie można wykonać operacji: {detail}")
                    raise ReportsApiError("Niepoprawne dane logów. Sprawdź format i długość wpisów.")
                raise ReportsApiError("Niepoprawne filtry. Sprawdź zakres dat.")
            if response.status_code in (502, 503, 504):
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else None
                if isinstance(detail, str):
                    raise ReportsApiError(detail)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as error:
            raise ReportsApiError("API nie odpowiedziało na czas. Spróbuj ponownie.") from error
        except httpx.RequestError as error:
            raise ReportsApiError("Nie można połączyć się z API. Sprawdź, czy jest uruchomione.") from error
        except httpx.HTTPStatusError as error:
            raise ReportsApiError("API nie może teraz obsłużyć żądania. Spróbuj ponownie.") from error
        except ValueError as error:
            raise ReportsApiError("API zwróciło odpowiedź w niepoprawnym formacie.") from error

    def history(self, **params) -> ReportHistory:
        try:
            return ReportHistory.model_validate(self._request("GET", "/api/v1/reports", params=params))
        except ValidationError as error:
            raise ReportsApiError("Odpowiedź API nie jest zgodna ze strukturą historii.") from error

    def report(self, report_id: str) -> RaportZdarzen:
        try:
            return RaportZdarzen.model_validate(self._request("GET", f"/api/v1/reports/{report_id}"))
        except ValidationError as error:
            raise ReportsApiError("Zapisany raport nie ma wymaganej struktury.") from error

    def analyze(self, request: AnalyzeRequest) -> AnalysisResponse:
        try:
            return AnalysisResponse.model_validate(self._request(
                "POST", "/api/v1/analyze", payload=request.model_dump(mode="json"),
            ))
        except ValidationError as error:
            raise ReportsApiError("Wynik analizy nie jest zgodny z kontraktem danych.") from error

    def generate_report(self, analysis_id: str, group_id: str | None = None, *, finding_id: str | None = None) -> RaportZdarzen:
        try:
            return RaportZdarzen.model_validate(self._request(
                "POST", f"/api/v1/analyses/{analysis_id}/reports",
                payload={"finding_id": finding_id} if finding_id else {"group_id": group_id}, timeout=150.0,
            ))
        except ValidationError as error:
            raise ReportsApiError("Wygenerowany raport nie ma wymaganej struktury.") from error

    def evaluation(self) -> EvaluationResults:
        try:
            return EvaluationResults.model_validate(self._request("GET", "/api/v1/evaluation"))
        except ValidationError as error:
            raise ReportsApiError("Wyniki eksperymentów nie są zgodne z kontraktem danych.") from error

    def findings(self, **params) -> FindingHistory:
        try:
            return FindingHistory.model_validate(self._request("GET", "/api/v1/findings", params=params))
        except ValidationError as error:
            raise ReportsApiError("Lista wykryć nie ma wymaganej struktury.") from error

    def finding(self, finding_id: str) -> Finding:
        try:
            return Finding.model_validate(self._request("GET", f"/api/v1/findings/{finding_id}"))
        except ValidationError as error:
            raise ReportsApiError("Wykrycie nie ma wymaganej struktury.") from error

    def analysis(self, analysis_id: str) -> AnalysisResponse:
        try:
            return AnalysisResponse.model_validate(self._request("GET", f"/api/v1/analyses/{analysis_id}"))
        except ValidationError as error:
            raise ReportsApiError("Analiza nie ma wymaganej struktury.") from error
