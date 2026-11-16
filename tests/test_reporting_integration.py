import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApi
from log_analyzer.reporting import ollama_klient
from log_analyzer.storage import sqlite_repo


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ollama_client(monkeypatch):
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=json.dumps({
        "podsumowanie": "Opis przekazanych zdarzeń.",
        "rekomendacja": "Zweryfikować kontekst zdarzeń.",
    })))
    monkeypatch.setattr(ollama_klient, "Client", lambda **kwargs: client)
    return client


def analyze(backend, log_format="ssh"):
    payload = json.loads((ROOT / f"data/samples/{log_format}_request.json").read_text(encoding="utf-8"))
    response = backend.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("log_format", ["ssh", "hdfs"])
def test_analysis_report_history_roundtrip(ollama_client, log_format):
    backend = TestClient(app)
    analysis = analyze(backend, log_format)
    assert backend.get(f"/api/v1/analyses/{analysis['analysis_id']}").json() == analysis
    group = analysis["groups"][0]
    response = backend.post(f"/api/v1/analyses/{analysis['analysis_id']}/reports", json={
        "group_id": group["group_id"],
    })
    assert response.status_code == 201
    report = response.json()
    assert report["event_ids"] == group["event_ids"]
    assert report["analysis_id"] == analysis["analysis_id"]
    assert report["group_id"] == group["group_id"]
    assert report["generation_mode"] == "manual"
    source = {event["event_id"]: event["raw"] for event in analysis["events"]}
    assert report["tresc"]["kluczowe_zdarzenia"] == [f"{eid}: {source[eid]}" for eid in group["event_ids"]]
    assert backend.get(f"/api/v1/reports/{report['report_id']}").json() == report
    assert backend.get("/api/v1/reports").json()["total"] == 1
    assert backend.get(f"/api/v1/analyses/{analysis['analysis_id']}").json()["detection_status"] == "not_configured"
    ollama_client.chat.assert_called_once()


def test_unknown_analysis_group_and_forged_sources_do_not_call_llm(ollama_client):
    backend = TestClient(app)
    assert backend.post(f"/api/v1/analyses/{uuid4()}/reports", json={"group_id": "x"}).status_code == 404
    analysis = analyze(backend)
    url = f"/api/v1/analyses/{analysis['analysis_id']}/reports"
    assert backend.post(url, json={"group_id": "not-in-analysis"}).status_code == 422
    assert backend.post(url, json={"group_id": "server01", "events": [{"raw": "fake"}]}).status_code == 422
    ollama_client.chat.assert_not_called()


@pytest.mark.parametrize("failure,status", [
    (ConnectionError("offline"), 503),
    (httpx.ReadTimeout("timeout"), 504),
])
def test_ollama_failure_preserves_analysis_without_creating_report(ollama_client, failure, status):
    backend = TestClient(app)
    analysis = analyze(backend)
    ollama_client.chat.side_effect = failure
    response = backend.post(f"/api/v1/analyses/{analysis['analysis_id']}/reports", json={"group_id": "server01"})
    assert response.status_code == status
    assert backend.get(f"/api/v1/analyses/{analysis['analysis_id']}").status_code == 200
    assert backend.get("/api/v1/reports").json()["total"] == 0


def test_invalid_llm_json_is_not_saved(ollama_client):
    backend = TestClient(app)
    analysis = analyze(backend)
    ollama_client.chat.return_value.message.content = '{"unexpected": "value"}'
    response = backend.post(f"/api/v1/analyses/{analysis['analysis_id']}/reports", json={"group_id": "server01"})
    assert response.status_code == 502
    assert backend.get("/api/v1/reports").json()["total"] == 0


def test_empty_llm_response_is_a_generator_error_and_is_not_saved(ollama_client):
    backend = TestClient(app)
    analysis = analyze(backend)
    ollama_client.chat.return_value.message.content = "  "
    response = backend.post(f"/api/v1/analyses/{analysis['analysis_id']}/reports", json={"group_id": "server01"})
    assert response.status_code == 502
    assert backend.get("/api/v1/reports").json()["total"] == 0


def test_large_group_uses_explicit_aggregation_and_preserves_all_sources(ollama_client):
    backend = TestClient(app)
    line = "Nov 4 10:14:03 server01 sshd[1234]: Failed password for admin from 192.0.2.10 port 51234 ssh2"
    analysis = backend.post("/api/v1/analyze", json={"log_format": "ssh", "logs": [line] * 21}).json()
    response = backend.post(f"/api/v1/analyses/{analysis['analysis_id']}/reports", json={"group_id": "server01"})
    assert response.status_code == 201
    report = response.json()
    assert report["llm_input_mode"] == "aggregated"
    assert report["liczba_zdarzen"] == len(report["event_ids"]) == 21
    assert len(report["tresc"]["kluczowe_zdarzenia"]) == 21
    assert len(report["llm_event_ids"]) + report["llm_omitted_events"] == 21
    ollama_client.chat.assert_called_once()
    assert set(ollama_client.chat.call_args.kwargs["format"]["properties"]) == {"podsumowanie", "rekomendacja"}


def test_missing_analysis_read_does_not_create_database():
    assert TestClient(app).get(f"/api/v1/analyses/{uuid4()}").status_code == 404
    assert not sqlite_repo.SCIEZKA_BAZY.exists()


def test_dashboard_can_generate_and_open_report_through_real_api(ollama_client, monkeypatch):
    backend = TestClient(app)

    def respond(request):
        response = backend.request(
            request.method, request.url.path,
            json=json.loads(request.content) if request.content else None,
        )
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(api_client, "ReportsApi", lambda url: ReportsApi(url, transport=httpx.MockTransport(respond)))
    page = AppTest.from_file(str(ROOT / "src/log_analyzer/dashboard/app.py"), default_timeout=15)
    page.query_params["view"] = "analysis"
    page.run()
    payload = json.loads((ROOT / "data/samples/ssh_request.json").read_text(encoding="utf-8"))
    page.text_area(key="analysis_text").set_value("\n".join(payload["logs"]))
    page.button(key="submit_analysis").click().run()
    page.button(key="generate_group_report").click().run()
    assert not page.exception and not page.error
    assert page.success
    page.button(key="open_analysis_report").click().run()
    assert not page.exception
    assert page.title[0].value == "Szczegóły raportu"
    assert payload["logs"][0] in page.code[0].value
    page.button(key="back_from_report").click().run()
    assert not page.exception
    assert page.button(key="generate_group_report").disabled
    ollama_client.chat.assert_called_once()
