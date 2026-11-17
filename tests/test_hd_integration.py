import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import joblib
import pytest
from fastapi.testclient import TestClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApi
from log_analyzer.reporting import ollama_klient
from test_hdfs_rules import line


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/log_analyzer/dashboard/app.py"


@pytest.fixture
def model_file(tmp_path, monkeypatch):
    # Wyłącznie deterministyczny model testowy; nie nadpisuje artefaktu HD.
    model = Pipeline([
        ("tfidf", TfidfVectorizer(token_pattern=r"(?u)\b[a-zA-Z]{3,}\b")),
        ("classifier", LogisticRegression(random_state=42)),
    ])
    model.fit([line("normal healthy stable blk_1")] * 3 + [line("error anomalous failed blk_2")] * 3,
              [0] * 3 + [1] * 3)
    path = tmp_path / "baseline.joblib"
    joblib.dump(model, path)
    monkeypatch.setenv("DETECTION_MODEL_PATH", str(path))
    return path


def analyze_ml(backend):
    response = backend.post("/api/v1/analyze", json={"logs": [
        line("normal healthy stable blk_1"), line("error anomalous failed blk_2"),
    ], "log_format": "hdfs", "data_scope": "sample"})
    assert response.status_code == 200
    return response.json()


def connect_dashboard(monkeypatch, backend):
    def respond(request):
        response = backend.request(request.method, request.url.path, params=request.url.params,
                                   json=json.loads(request.content) if request.content else None)
        return httpx.Response(response.status_code, json=response.json())
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: ReportsApi(url, transport=httpx.MockTransport(respond)))


def test_model_predictions_and_evidence_are_saved_with_analysis(model_file):
    backend = TestClient(app)
    result = analyze_ml(backend)
    assert backend.get("/health").json()["detection"] == "configured"
    assert result["detection_status"] == "completed"
    assert [group["ml_prediction"] for group in result["groups"]] == ["normal", "anomaly"]
    assert result["groups"][0]["ml_score"] < 0.5 < result["groups"][1]["ml_score"]
    finding = result["findings"][0]
    assert finding["source"] == "ml" and finding["rule_ids"] == []
    assert finding["event_ids"] == [result["events"][1]["event_id"]]
    assert finding["details"]["group_id"] == "blk_2"
    assert backend.get("/api/v1/analyses/" + result["analysis_id"]).json() == result
    assert backend.get("/api/v1/findings/" + finding["finding_id"]).json() == finding


def test_ml_report_uses_new_schema_and_opens_in_dashboard(model_file, monkeypatch):
    backend = TestClient(app)
    result = analyze_ml(backend)
    finding = result["findings"][0]
    llm = MagicMock()
    llm.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=json.dumps({
        "obserwacja": "Wpis źródłowy zawiera komunikat błędu.",
        "powod_wskazania": "Model wskazał grupę zdarzeń do sprawdzenia.",
        "ograniczenia_oceny": ["Model jest testowy; wynik nie potwierdza incydentu."],
        "zalecenia": ["Przejrzeć zdarzenia źródłowe.", "Sprawdzić kontekst operacji."],
    })))
    monkeypatch.setattr(ollama_klient, "Client", lambda **kwargs: llm)
    connect_dashboard(monkeypatch, backend)
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params.update(view="finding", finding_id=finding["finding_id"])
    page.run()
    assert not page.exception and not page.error
    assert not any("Dopasowane reguły" in item.value for item in page.caption)
    assert any("blk_2" in item.value for item in page.caption)
    page.button(key="generate_finding_report").click().run()
    page.button(key="open_finding_report").click().run()
    assert not page.exception and not page.error
    assert page.title[0].value == "Szczegóły raportu"
    report = backend.get("/api/v1/reports/" + page.query_params["report_id"]).json()
    assert report["tresc"]["schema_version"] == 2 and report["finding"]["source"] == "ml"
    assert report["event_ids"] == finding["event_ids"]
    assert backend.get("/api/v1/reports").json()["total"] == 1


def test_streaming_import_and_ip_filters_keep_model_predictions(model_file, monkeypatch):
    backend = TestClient(app)
    raw = line("error anomalous failed blk_2 peer 192.0.2.10")
    response = backend.post("/api/v1/analyze/file", params={"log_format": "hdfs"},
                            content=iter([raw[:30].encode(), raw[30:].encode()]))
    assert response.status_code == 200 and response.json()["finding_count"] == 1
    result = backend.get("/api/v1/analyses/" + response.json()["analysis_id"]).json()
    connect_dashboard(monkeypatch, backend)
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params.update(view="analysis", analysis_id=result["analysis_id"])
    page.run()
    assert not page.exception and not page.error
    assert "anomaly" in page.dataframe[1].value.iloc[0]["Ocena ML"]
    page.selectbox(key=f"any_ip_{result['analysis_id']}").set_value("192.0.2.10").run()
    assert len(page.dataframe[0].value) == 1 and not page.exception


def test_multiblock_entry_is_not_claimed_as_evidence_for_secondary_block(model_file):
    result = TestClient(app).post("/api/v1/analyze", json={"logs": [
        line("normal healthy stable blk_1 blk_2"), line("error anomalous failed blk_2"),
    ]}).json()
    ml_finding = next(item for item in result["findings"] if item["source"] == "ml")
    assert ml_finding["event_ids"] == [result["events"][1]["event_id"]]


def test_secondary_only_group_is_marked_unassessed(model_file):
    result = TestClient(app).post("/api/v1/analyze", json={"logs": [line("normal healthy stable blk_1 blk_2")]}).json()
    assert result["detection_status"] == "partial"
    assert result["groups"][0]["ml_prediction"] == "normal"
    assert result["groups"][1]["ml_prediction"] is None


def test_model_is_not_used_for_ssh(model_file):
    raw = "Nov 4 10:14:03 server01 sshd[1]: Failed password for admin from 192.0.2.10 port 1234 ssh2"
    result = TestClient(app).post("/api/v1/analyze", json={"logs": [raw], "log_format": "ssh"}).json()
    assert result["detection_status"] == "not_configured"
    assert result["groups"][0]["ml_prediction"] is None


def test_missing_or_empty_artifact_does_not_break_parsing(tmp_path, monkeypatch):
    path = tmp_path / "missing.joblib"
    monkeypatch.setenv("DETECTION_MODEL_PATH", str(path))
    backend = TestClient(app)
    assert analyze_ml(backend)["detection_status"] == "not_configured"
    path.write_bytes(b"")
    result = analyze_ml(backend)
    assert result["detection_status"] == "partial" and not result["findings"]


def test_hd_test_metrics_are_visible_without_model_or_retraining(monkeypatch):
    monkeypatch.setenv("EVALUATION_RESULTS_PATH", str(ROOT / "reports/training_metrics_20261117_123831.json"))
    backend = TestClient(app)
    connect_dashboard(monkeypatch, backend)
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params["view"] = "evaluation"
    page.run()
    assert not page.exception and not page.error
    assert [item.value for item in page.metric][:3] == ["0.9232", "0.9997", "0.9599"]
    assert page.selectbox[1].options == ["Test"]
    assert len(page.dataframe) == 2
    assert page.dataframe[0].value.iloc[0, 2] == 280
    assert page.dataframe[0].value.iloc[1, 1] == 1


def test_repository_hdfs_artifact_loads_and_predictions_are_saved(monkeypatch):
    path = ROOT / "models/baseline.joblib"
    assert path.is_file()
    monkeypatch.setenv("DETECTION_MODEL_PATH", str(path))
    payload = json.loads((ROOT / "data/samples/hdfs_request.json").read_text(encoding="utf-8"))
    backend = TestClient(app)
    response = backend.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["detection_status"] == "completed"
    assert all(group["ml_prediction"] in ("normal", "anomaly") for group in result["groups"])
    assert all(0 <= group["ml_score"] <= 1 for group in result["groups"])
    assert backend.get("/api/v1/analyses/" + result["analysis_id"]).json() == result
