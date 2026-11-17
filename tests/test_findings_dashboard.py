import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import streamlit
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApi
from log_analyzer.reporting import ollama_klient


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/log_analyzer/dashboard/app.py"
WARN = "081109 203615 148 WARN dfs.DataNode$DataXceiver: 10.0.0.1:50010:Got exception while serving blk_1 to /10.0.0.2:"


@pytest.fixture
def connected_api(monkeypatch):
    backend = TestClient(app)
    analysis = backend.post("/api/v1/analyze", json={"logs": [WARN], "log_format": "hdfs", "data_scope": "sample"}).json()

    def respond(request):
        response = backend.request(request.method, request.url.path, params=request.url.params,
                                   json=json.loads(request.content) if request.content else None)
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(api_client, "ReportsApi", lambda url: ReportsApi(url, transport=httpx.MockTransport(respond)))
    return backend, analysis


def test_findings_list_detail_and_report_roundtrip(connected_api, monkeypatch):
    backend, analysis = connected_api
    llm = MagicMock()
    llm.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=json.dumps({
        "obserwacja": "Wyjątek podczas udostępniania bloku.",
        "powod_wskazania": "Reguła wskazuje komunikat o wyjątku.",
        "ograniczenia_oceny": ["Przyczyna wyjątku nie jest znana."],
        "zalecenia": ["Sprawdzić kontekst operacji.", "Przejrzeć powiązane logi węzła."],
    })))
    monkeypatch.setattr(ollama_klient, "Client", lambda **kwargs: llm)
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params.update(view="finding", finding_id=analysis["findings"][0]["finding_id"])
    page.run()
    assert not page.exception and not page.error
    assert "reguły" in page.warning[0].value.casefold()
    assert WARN in page.code[0].value
    page.button(key="generate_finding_report").click().run()
    assert not page.exception and not page.error
    page.button(key="open_finding_report").click().run()
    assert not page.exception and page.title[0].value == "Szczegóły raportu"
    report = backend.get(f"/api/v1/reports/{page.query_params['report_id']}").json()
    assert report["finding"]["finding_id"] == analysis["findings"][0]["finding_id"]
    assert report["event_ids"] == analysis["findings"][0]["event_ids"]
    assert report["czas_zrodlowy_od"] == "2008-11-09T20:36:15"
    page.button(key="back_from_report").click().run()
    assert not page.exception and page.title[0].value == "Szczegóły wykrycia"
    assert page.button(key="generate_finding_report").disabled
    llm.chat.assert_called_once()


def test_findings_selection_and_filters_use_real_api(connected_api, monkeypatch):
    backend, analysis = connected_api
    monkeypatch.setattr(streamlit, "dataframe", lambda *args, **kwargs: SimpleNamespace(selection=SimpleNamespace(rows=[0])))
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params["view"] = "findings"
    page.run()
    assert not page.exception and not page.error
    page.text_input(key="finding_query").set_value("not-present").run()
    assert page.info and not page.exception
    page.text_input(key="finding_query").set_value("10.0.0.1").run()
    page.button(key="open_finding").click().run()
    assert not page.exception and page.title[0].value == "Szczegóły wykrycia"
    assert page.query_params["finding_id"] == analysis["findings"][0]["finding_id"]


def test_report_cannot_use_finding_from_another_analysis(connected_api):
    backend, analysis = connected_api
    second = backend.post("/api/v1/analyze", json={"logs": [WARN]}).json()
    response = backend.post(f"/api/v1/analyses/{second['analysis_id']}/reports", json={"finding_id": analysis["findings"][0]["finding_id"]})
    assert response.status_code == 422


def test_report_requires_exactly_one_source(connected_api):
    backend, analysis = connected_api
    url = f"/api/v1/analyses/{analysis['analysis_id']}/reports"
    assert backend.post(url, json={}).status_code == 422
    assert backend.post(url, json={"group_id": "blk_1", "finding_id": analysis["findings"][0]["finding_id"]}).status_code == 422


def test_analysis_filters_show_level_and_source_details(connected_api, monkeypatch):
    backend, analysis = connected_api
    monkeypatch.setattr(streamlit, "dataframe", lambda *args, **kwargs: SimpleNamespace(selection=SimpleNamespace(rows=[0])))
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params["view"] = "analysis"
    page.session_state["analysis_result"] = analysis
    page.run()
    assert not page.exception
    assert WARN in page.code[0].value
    page.text_input(key=f"search_{analysis['analysis_id']}").set_value("not-present").run()
    assert not page.exception and not page.code


def test_findings_page_has_no_manual_case_status(connected_api):
    _, analysis = connected_api
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params.update(view="finding", finding_id=analysis["findings"][0]["finding_id"])
    page.run()
    assert not page.exception
    assert all("Zamknij" not in button.label for button in page.button)
    assert all("status" not in widget.label.lower() for widget in page.selectbox)
