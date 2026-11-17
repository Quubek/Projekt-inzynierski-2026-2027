import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.contracts import OpisRaportu, RaportZdarzen, TrescRaportu, UstrukturyzowanaTrescRaportu
from log_analyzer.dashboard import api_client
from log_analyzer.storage import sqlite_repo
from test_report_history import make_report


def structured_content():
    return {
        "obserwacja": "Zarejestrowano żądanie usunięcia 100 bloków.",
        "powod_wskazania": "Liczba bloków przekroczyła próg reguły.",
        "ograniczenia_oceny": ["Żądanie nie potwierdza wykonania operacji."],
        "zalecenia": ["Sprawdzić, czy operacja była zaplanowana.", "Przejrzeć powiązane logi węzła."],
    }


def new_report():
    data = make_report(2, "2026-11-17T10:00:00Z", None).model_dump(mode="json")
    data["tresc"] = {**structured_content(), "schema_version": 2, "kluczowe_zdarzenia": ["event-2: źródłowy log"]}
    data["prompt_version"] = "log-report-v2"
    data["llm_model"] = "qwen3:4b-instruct"
    return RaportZdarzen.model_validate(data)


@pytest.mark.parametrize("change", [
    {"obserwacja": "  "},
    {"zalecenia": "Sprawdzić logi"},
    {"zalecenia": ["Tylko jedna czynność"]},
    {"zalecenia": ["a", "b", "c", "d"]},
    {"zalecenia": ["a", "  "]},
    {"ograniczenia_oceny": "Brak kontekstu"},
    {"priority": "critical"},
])
def test_model_output_requires_sections_and_a_valid_action_list(change):
    with pytest.raises(ValidationError):
        OpisRaportu.model_validate({**structured_content(), **change})


def test_empty_limitations_are_allowed_without_inventing_missing_information():
    content = OpisRaportu.model_validate({**structured_content(), "ograniczenia_oceny": []})
    assert content.ograniczenia_oceny == []


def test_sources_preserve_whitespace_instead_of_normalizing_original_evidence():
    source = "event-2: original log with trailing spaces  "
    content = UstrukturyzowanaTrescRaportu(**structured_content(), kluczowe_zdarzenia=[source])
    assert content.kluczowe_zdarzenia == [source]


def test_new_and_legacy_reports_share_history_without_rewriting_saved_data():
    sqlite_repo.inicjalizuj_baze()
    old = make_report(1, "2026-11-16T10:00:00Z", None)
    raw_old = old.model_dump_json(exclude={"prompt_version", "llm_model"})
    sqlite_repo.zapisz_raport(raw_old)
    current = new_report()
    sqlite_repo.zapisz_raport(current.model_dump_json())
    client = TestClient(app)
    history = client.get("/api/v1/reports").json()
    assert history["reports"][0]["podsumowanie"] == current.tresc.obserwacja
    assert history["reports"][1]["podsumowanie"] == old.tresc.podsumowanie
    legacy = RaportZdarzen.model_validate(client.get(f"/api/v1/reports/{old.report_id}").json())
    modern = RaportZdarzen.model_validate(client.get(f"/api/v1/reports/{current.report_id}").json())
    assert isinstance(legacy.tresc, TrescRaportu)
    assert isinstance(modern.tresc, UstrukturyzowanaTrescRaportu)
    assert sqlite_repo.pobierz_raport(str(old.report_id)) == raw_old


def test_dashboard_renders_fixed_sections_and_numbers_actions(monkeypatch):
    report = new_report()
    client = MagicMock()
    client.__enter__.return_value = client
    client.report.return_value = report
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: client)
    path = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"
    page = AppTest.from_file(str(path), default_timeout=15)
    page.query_params.update(view="report", report_id=str(report.report_id))
    page.run()
    assert not page.exception
    assert [item.value for item in page.subheader][:4] == [
        "Obserwacja", "Powód wskazania", "Ograniczenia oceny", "Zalecane sprawdzenia",
    ]
    assert any(item.value == "1. Sprawdzić, czy operacja była zaplanowana." for item in page.text)
    assert any(item.value == "2. Przejrzeć powiązane logi węzła." for item in page.text)
    assert any(item.value == "• Żądanie nie potwierdza wykonania operacji." for item in page.text)
    assert json.loads(report.model_dump_json())["tresc"]["zalecenia"] == report.tresc.zalecenia
