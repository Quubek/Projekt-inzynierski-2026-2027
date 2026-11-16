import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from log_analyzer.api.main import app
from log_analyzer.contracts import RaportZdarzen
from log_analyzer.dashboard.api_client import ReportsApi, ReportsApiError
from log_analyzer.storage import sqlite_repo


def make_report(number, created_at, host):
    return RaportZdarzen.model_validate({
        "report_id": str(UUID(int=number)), "created_at": created_at,
        "event_ids": [f"event-{number}"], "host": host,
        "liczba_zdarzen": 1, "liczba_zdarzen_bez_czasu": 1,
        "czas_od": None, "czas_do": None,
        "tresc": {
            "podsumowanie": f"Przykładowy raport {number}.",
            "kluczowe_zdarzenia": [f"event-{number}: źródłowy log"],
            "rekomendacja": "Sprawdzić kontekst zdarzenia.",
        },
    })


@pytest.fixture
def history_client(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", tmp_path / "reports.sqlite3")
    sqlite_repo.inicjalizuj_baze()
    for number, host in ((1, "server01"), (2, "server02"), (3, None)):
        report = make_report(number, f"2026-11-0{number + 3}T10:00:00Z", host)
        sqlite_repo.zapisz_raport(report.model_dump_json())
    return TestClient(app)


def test_history_counts_and_pagination(history_client):
    response = history_client.get("/api/v1/reports", params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3 and data["known_host_count"] == 2
    assert data["known_hosts"] == ["server01", "server02"]
    assert len(data["reports"]) == 1
    assert data["reports"][0]["report_id"] == str(UUID(int=2))
    assert data["latest_created_at"] == "2026-11-06T10:00:00Z"
    assert history_client.get("/api/v1/reports?offset=100").json()["reports"] == []


def test_host_and_id_filters(history_client):
    data = history_client.get("/api/v1/reports?host=server01").json()
    assert data["total"] == 1 and data["known_host_count"] == 1
    assert data["reports"][0]["host"] == "server01"
    unknown = history_client.get("/api/v1/reports?unknown_host=true").json()
    assert unknown["total"] == 1 and unknown["known_host_count"] == 0
    assert unknown["reports"][0]["host"] is None
    found = history_client.get("/api/v1/reports", params={"report_id_query": "000000000002"}).json()
    assert found["total"] == 1 and found["reports"][0]["host"] == "server02"
    for params in ({"report_id_query": "%"}, {"host": "x' OR 1=1 --"}):
        assert history_client.get("/api/v1/reports", params=params).json()["total"] == 0


def test_date_filter_uses_timezone_and_exclusive_upper_bound(history_client):
    data = history_client.get("/api/v1/reports", params={
        "created_from": "2026-11-05T11:00:00+01:00",
        "created_before": "2026-11-06T00:00:00Z",
    }).json()
    assert data["total"] == 1
    assert data["reports"][0]["report_id"] == str(UUID(int=2))


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"offset": -1},
    {"host": "server01", "unknown_host": True},
    {"created_from": "2026-11-05T10:00:00"},
    {"created_from": "2026-11-06T00:00:00Z", "created_before": "2026-11-05T00:00:00Z"},
])
def test_invalid_history_filters(history_client, params):
    assert history_client.get("/api/v1/reports", params=params).status_code == 422


def test_empty_history_does_not_create_database(tmp_path, monkeypatch):
    path = tmp_path / "missing" / "reports.sqlite3"
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", path)
    response = TestClient(app).get("/api/v1/reports")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["reports"] == []
    assert not path.exists() and not path.parent.exists()


def test_database_error_returns_service_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "broken.sqlite3"
    path.write_text("not a database", encoding="utf-8")
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", path)
    client = TestClient(app)
    assert client.get("/api/v1/reports").status_code == 503
    assert client.get(f"/api/v1/reports/{UUID(int=1)}").status_code == 503


def test_history_and_detail_are_compatible_with_dashboard(history_client):
    def respond(request):
        result = history_client.get(request.url.path, params=request.url.params)
        return httpx.Response(result.status_code, json=result.json())

    with ReportsApi("http://testserver", transport=httpx.MockTransport(respond)) as api:
        history = api.history(host="server01")
        report = api.report(str(history.reports[0].report_id))
        assert report.host == "server01"
        assert "źródłowy log" in report.model_dump_json()


@pytest.mark.parametrize("status,body", [
    (404, {}), (503, {}), (200, {"unexpected": True}),
])
def test_dashboard_handles_unavailable_or_invalid_api(status, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with ReportsApi("http://testserver", transport=transport) as api:
        with pytest.raises(ReportsApiError):
            api.history()


def test_dashboard_handles_connection_error():
    def disconnect(request):
        raise httpx.ConnectError("connection refused", request=request)

    with ReportsApi("http://testserver", transport=httpx.MockTransport(disconnect)) as api:
        with pytest.raises(ReportsApiError, match="połączyć"):
            api.history()
