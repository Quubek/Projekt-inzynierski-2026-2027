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
from test_hdfs_rules import line


APP = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"


@pytest.fixture
def llm(monkeypatch):
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=json.dumps({
        "obserwacja": "Opis wybranych zdarzeń.",
        "powod_wskazania": "Grupy zostały wybrane ręcznie.",
        "ograniczenia_oceny": ["Nie potwierdzono związku między grupami."],
        "zalecenia": ["Sprawdzić kontekst grup.", "Przejrzeć źródłowe logi."],
    })))
    monkeypatch.setattr(ollama_klient, "Client", lambda **kwargs: client)
    return client


def analysis(backend):
    response = backend.post("/api/v1/analyze", json={"logs": [
        line("Receiving block blk_1 src: /10.0.0.1:1234 dest: /10.0.0.2:50010"),
        line("BLOCK* ask 10.0.0.2:50010 to replicate blk_1 blk_2"),
        line("Received block blk_2 of size 100 from /10.0.0.1"),
        line("Deleting block blk_3 file /tmp/blk_3"),
    ]})
    assert response.status_code == 200
    return response.json()


def test_multiple_groups_deduplicate_sources_and_keep_source_order(llm):
    backend = TestClient(app)
    result = analysis(backend)
    response = backend.post(f"/api/v1/analyses/{result['analysis_id']}/reports",
                            json={"group_ids": ["blk_2", "blk_1"]})
    assert response.status_code == 201
    report = response.json()
    assert report["group_id"] is None and report["group_ids"] == ["blk_1", "blk_2"]
    assert report["event_ids"] == [event["event_id"] for event in result["events"][:3]]
    assert report["liczba_zdarzen"] == 3 and len(report["tresc"]["kluczowe_zdarzenia"]) == 3
    payload = json.loads(llm.chat.call_args.kwargs["messages"][1]["content"])
    assert payload["total_events"] == 3
    assert payload["context"]["manual_selection"] == {
        "group_count": 2, "group_ids_preview": ["blk_1", "blk_2"],
        "omitted_group_ids": 0, "related_incident_confirmed": False,
    }
    assert backend.get("/api/v1/reports/" + report["report_id"]).json() == report


@pytest.mark.parametrize("payload", [
    {"group_ids": []}, {"group_ids": [""]}, {"group_ids": ["blk_1", "blk_1"]},
    {"group_ids": ["not-in-analysis"]}, {"group_ids": ["blk_1", "not-in-analysis"]},
    {"group_id": "blk_1", "group_ids": ["blk_2"]},
    {"finding_id": str(uuid4()), "group_ids": ["blk_1"]},
    {"group_ids": ["blk_1"], "events": [{"raw": "forged"}]},
])
def test_invalid_selection_never_calls_llm_or_saves_partial_report(llm, payload):
    backend = TestClient(app)
    result = analysis(backend)
    response = backend.post(f"/api/v1/analyses/{result['analysis_id']}/reports", json=payload)
    assert response.status_code == 422
    llm.chat.assert_not_called()
    assert backend.get("/api/v1/reports").json()["total"] == 0


def test_ssh_groups_with_different_hosts_share_a_report_and_history_filters(llm):
    backend = TestClient(app)
    raw = "Nov 4 10:14:03 {host} sshd[1]: Failed password for admin from 192.0.2.10 port 1234 ssh2"
    result = backend.post("/api/v1/analyze", json={"log_format": "ssh", "logs": [
        raw.format(host="server01"), raw.format(host="server02"),
    ]}).json()
    report = backend.post(f"/api/v1/analyses/{result['analysis_id']}/reports",
                          json={"group_ids": ["server01", "server02"]}).json()
    assert report["host"] is None and report["hosts"] == ["server01", "server02"]
    assert report["liczba_zdarzen_bez_hosta"] == 0
    for host in ("server01", "server02"):
        history = backend.get("/api/v1/reports", params={"host": host}).json()
        assert history["total"] == 1 and history["known_host_count"] == 2
    history = backend.get("/api/v1/reports").json()
    assert history["known_hosts"] == ["server01", "server02"]
    assert history["reports"][0]["hosts"] == ["server01", "server02"]
    assert backend.get("/api/v1/reports", params={"unknown_host": True}).json()["total"] == 0


def test_partial_host_information_is_preserved_and_searchable(llm):
    events = [{"event_id": f"e{i}", "raw": "source", "host": host} for i, host in enumerate(["server01", None])]
    report = ollama_klient.generuj_raport(events)
    assert report.host is None and report.hosts == ["server01"]
    assert report.liczba_zdarzen_bez_hosta == 1
    sqlite_repo.inicjalizuj_baze()
    sqlite_repo.zapisz_raport(report.model_dump_json())
    backend = TestClient(app)
    assert backend.get("/api/v1/reports", params={"host": "server01"}).json()["total"] == 1
    assert backend.get("/api/v1/reports", params={"unknown_host": True}).json()["total"] == 1


def test_many_selected_groups_keep_all_metadata_and_explicit_aggregation(llm):
    backend = TestClient(app)
    result = backend.post("/api/v1/analyze", json={"logs": [
        line(f"Received block blk_{index} of size 100 from /10.0.0.1") for index in range(30)
    ]}).json()
    report = backend.post(f"/api/v1/analyses/{result['analysis_id']}/reports",
                          json={"group_ids": [group["group_id"] for group in result["groups"]]}).json()
    assert len(report["group_ids"]) == report["liczba_zdarzen"] == 30
    assert len(report["event_ids"]) == 30 and report["llm_input_mode"] == "aggregated"
    payload = json.loads(llm.chat.call_args.kwargs["messages"][1]["content"])
    assert payload["context"]["manual_selection"]["group_count"] == 30
    assert payload["context"]["manual_selection"]["omitted_group_ids"] == 20
    assert len(report["tresc"]["kluczowe_zdarzenia"]) == 30


def test_dashboard_selects_groups_counts_unique_events_and_keeps_selection(llm, monkeypatch):
    backend = TestClient(app)
    result = analysis(backend)
    def respond(request):
        response = backend.request(request.method, request.url.path, params=request.url.params,
                                   json=json.loads(request.content) if request.content else None)
        return httpx.Response(response.status_code, json=response.json())
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: ReportsApi(url, transport=httpx.MockTransport(respond)))
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params.update(view="analysis", analysis_id=result["analysis_id"])
    page.run()
    key = f"report_groups_{result['analysis_id']}"
    page.multiselect(key=key).set_value(["blk_1", "blk_2"]).run()
    assert not page.exception
    assert any("Wybrano grupy: 2 · Unikalne zdarzenia: 3" == item.value for item in page.caption)
    page.button(key="generate_group_report").click().run()
    assert not page.exception and not page.error
    page.button(key="open_analysis_report").click().run()
    assert any("Wybrane grupy (2)" == item.label for item in page.expander)
    page.button(key="back_from_report").click().run()
    assert page.multiselect(key=key).value == ["blk_1", "blk_2"]
    assert page.button(key="generate_group_report").disabled
    page.multiselect(key=key).set_value(["blk_2", "blk_1"]).run()
    assert page.button(key="generate_group_report").disabled
    page.button(key="clear_report_groups").click().run()
    assert not page.multiselect(key=key).value and page.button(key="generate_group_report").disabled
    assert not page.exception
    llm.chat.assert_called_once()
