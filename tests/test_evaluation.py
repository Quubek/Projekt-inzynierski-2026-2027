import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApi


@pytest.fixture
def results_file(tmp_path, monkeypatch):
    path = tmp_path / "results.json"
    monkeypatch.setenv("EVALUATION_RESULTS_PATH", str(path))
    return path


def example_results():
    return {
        "model": "tfidf-logreg-v1", "date": "2026-11-16", "dataset": "synthetic-demo",
        "data_source": "synthetic", "class_labels": [0, 1],
        "split": {"train": 70, "val": 14, "test": 15},
        "validation": {
            "precision": 0.75, "recall": 0.6, "f1": 0.6667,
            "confusion_matrix": [[8, 1], [2, 3]], "n": 14,
        },
    }


def test_missing_results_are_empty_without_creating_file(results_file):
    response = TestClient(app).get("/api/v1/evaluation")
    assert response.status_code == 200 and response.json() == {"experiments": []}
    assert not results_file.exists()


def test_existing_hd_format_and_multiple_experiments(results_file):
    backend = TestClient(app)
    data = example_results()
    for content in (data, {"experiments": [data, {**data, "model": "embedding-classifier-v1"}]}):
        results_file.write_text(json.dumps(content), encoding="utf-8")
        response = backend.get("/api/v1/evaluation")
        assert response.status_code == 200
        assert response.json()["experiments"][0]["validation"]["f1"] == 0.6667
    assert len(response.json()["experiments"]) == 2


@pytest.mark.parametrize("mutation", [
    lambda data: data["validation"].update(f1=1.1),
    lambda data: data["validation"].update(confusion_matrix=[[14]]),
    lambda data: data["validation"].update(n=15),
    lambda data: data.update(class_labels=[1, 0]),
    lambda data: data["split"].update(val=20),
])
def test_invalid_metrics_are_not_displayed(results_file, mutation):
    data = example_results()
    mutation(data)
    results_file.write_text(json.dumps(data), encoding="utf-8")
    assert TestClient(app).get("/api/v1/evaluation").status_code == 503


def test_dashboard_reads_metrics_and_warns_about_synthetic_data(results_file, monkeypatch):
    results_file.write_text(json.dumps(example_results()), encoding="utf-8")
    backend = TestClient(app)

    def respond(request):
        response = backend.get(request.url.path)
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(api_client, "ReportsApi", lambda url: ReportsApi(url, transport=httpx.MockTransport(respond)))
    path = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"
    page = AppTest.from_file(str(path), default_timeout=15)
    page.query_params["view"] = "evaluation"
    page.run()
    assert not page.exception
    assert [item.value for item in page.metric] == ["0.7500", "0.6000", "0.6667"]
    assert any("syntetycznych" in warning.value for warning in page.warning)
    assert len(page.dataframe) == 1
    assert page.dataframe[0].value.iloc[1, 1] == 2
