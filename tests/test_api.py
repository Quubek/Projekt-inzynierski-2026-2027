import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from log_analyzer.api.main import app
from log_analyzer.storage import sqlite_repo

client = TestClient(app)
SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_hdfs_groups_and_templates():
    payload = json.loads((SAMPLES / "hdfs_request.json").read_text())
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 3
    assert sorted(len(group["event_ids"]) for group in data["groups"]) == [1, 2]
    first, second, _ = data["events"]
    assert first["template"] == second["template"]
    assert "1608999687919862906" not in first["template"]
    assert first["timestamp"] is None and first["timestamp_raw"] == "2008-11-09T20:35:18"
    assert first["host"] is None
    assert data["detection_status"] == "not_configured"
    assert "is_anomaly" not in data


def test_ssh_fields():
    payload = json.loads((SAMPLES / "ssh_request.json").read_text())
    data = client.post("/api/v1/analyze", json=payload).json()
    event = data["events"][0]
    assert event["host"] == "server01"
    assert event["parameters"]["source_ip"] == "192.0.2.10"
    assert event["parameters"]["user"] == "admin"
    assert event["timestamp"] is None
    assert event["raw"] == payload["logs"][0]


@pytest.mark.parametrize("payload", [
    {}, {"logs": []}, {"logs": [""]}, {"logs": ["   "]},
    {"logs": [123]}, {"logs": ["x"], "log_format": "unknown"},
    {"logs": ["x"]}, {"logs": ["x"] * 1001},
    {"logs": ["081332 203518 143 INFO dfs.DataNode: bad date"]},
])
def test_invalid_input(payload):
    assert client.post("/api/v1/analyze", json=payload).status_code == 422


def test_unique_event_ids_between_requests():
    payload = json.loads((SAMPLES / "hdfs_request.json").read_text())
    first = client.post("/api/v1/analyze", json=payload).json()
    second = client.post("/api/v1/analyze", json=payload).json()
    assert first["events"][0]["event_id"] != second["events"][0]["event_id"]


def test_read_existing_jf_report(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", tmp_path / "reports.sqlite3")
    sqlite_repo.inicjalizuj_baze()
    report = {"report_id": str(uuid4()), "created_at": "2026-11-04T12:00:00Z", "host": None}
    sqlite_repo.zapisz_raport(json.dumps(report))
    response = client.get(f"/api/v1/reports/{report['report_id']}")
    assert response.status_code == 200
    assert response.json() == report
    assert client.get(f"/api/v1/reports/{uuid4()}").status_code == 404


def test_missing_database(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", tmp_path / "missing.sqlite3")
    assert client.get(f"/api/v1/reports/{uuid4()}").status_code == 404
    assert not sqlite_repo.SCIEZKA_BAZY.exists()
