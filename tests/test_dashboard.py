from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from log_analyzer.contracts import EvaluationResults, ReportHistory
from log_analyzer.dashboard import api_client
from test_report_history import make_report


APP = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"


def mock_api(monkeypatch, *, empty=False, error=False):
    report = make_report(1, "2026-11-04T10:00:00Z", "server01")
    history = ReportHistory(
        reports=[] if empty else [{
            "report_id": report.report_id, "created_at": report.created_at,
            "host": report.host, "liczba_zdarzen": 1,
            "podsumowanie": report.tresc.podsumowanie,
        }],
        total=0 if empty else 1, known_hosts=[] if empty else ["server01"],
        known_host_count=0 if empty else 1,
        latest_created_at=None if empty else report.created_at, limit=25, offset=0,
    )
    api = MagicMock()
    api.__enter__.return_value = api
    api.history.return_value = history
    api.report.return_value = report
    api.evaluation.return_value = EvaluationResults()
    if error:
        api.history.side_effect = api_client.ReportsApiError("Nie można połączyć się z API.")
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: api)
    return api


def test_home_tiles_do_not_load_history(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP)).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == "Analizator logów"
    assert app.button(key="tile_history")
    assert app.button(key="tile_analysis")
    assert app.button(key="tile_evaluation")
    assert not app.dataframe and not app.text_input
    assert not app.sidebar.button
    assert not any(button.key == "back_to_home" for button in app.button)
    api.history.assert_not_called()


def test_history_is_a_separate_view_without_report_content(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP)).run(timeout=15)
    app.button(key="tile_history").click().run()
    assert not app.exception
    assert app.title[0].value == "Historia raportów"
    assert len(app.dataframe) == 1
    assert not app.get("download_button")
    assert not app.code
    assert app.button(key="open_report").disabled
    api.report.assert_not_called()
    app.button(key="back_to_home").click().run()
    assert not app.exception
    assert app.title[0].value == "Analizator logów"


def test_direct_report_link_opens_detail_and_download(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP))
    app.query_params.update(view="report", report_id=str(api.report.return_value.report_id))
    app.run(timeout=15)
    assert not app.exception
    assert app.title[0].value == "Szczegóły raportu"
    assert not app.dataframe and not app.text_input
    assert len(app.get("download_button")) == 1
    assert [tab.label for tab in app.tabs] == ["Podsumowanie", "Zdarzenia źródłowe", "Dane raportu"]
    assert any("źródłowy log" in element.value for element in app.code)
    assert app.warning
    assert app.button(key="back_to_home")
    assert app.button(key="back_from_report")
    assert not app.sidebar.button
    api.history.assert_not_called()


def test_dashboard_shows_empty_history(monkeypatch):
    mock_api(monkeypatch, empty=True)
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "history"
    app.run(timeout=15)
    assert not app.exception
    assert any("Historia jest pusta" in element.value for element in app.info)
    assert not app.dataframe


def test_dashboard_shows_connection_error(monkeypatch):
    mock_api(monkeypatch, error=True)
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "history"
    app.run(timeout=15)
    assert not app.exception
    assert "połączyć" in app.error[0].value


def test_dashboard_passes_filter_and_clears_it(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "history"
    app.run(timeout=15)
    app.text_input(key="filter_id").set_value("example-id").run()
    assert not app.exception
    assert any(call.kwargs.get("report_id_query") == "example-id" for call in api.history.call_args_list)
    app.button(key="clear_filters").click().run()
    assert not app.exception
    assert app.text_input(key="filter_id").value == ""


def test_back_from_report_preserves_history_filters_and_page(monkeypatch):
    api = mock_api(monkeypatch)
    api.history.return_value.total = 30
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "history"
    app.run(timeout=15)
    app.text_input(key="filter_id").set_value("example-id").run()
    app.date_input(key="filter_from").set_value(date(2026, 11, 3)).run()
    app.number_input(key="history_page").set_value(2).run()
    app.query_params.update(view="report", report_id=str(api.report.return_value.report_id))
    app.run(timeout=15)
    app.run(timeout=15)  # Widgety historii są już usunięte przez Streamlit.
    app.button(key="back_from_report").click().run()
    assert not app.exception
    assert app.title[0].value == "Historia raportów"
    assert app.text_input(key="filter_id").value == "example-id"
    assert app.date_input(key="filter_from").value == date(2026, 11, 3)
    assert app.number_input(key="history_page").value == 2


def test_open_selected_report_navigates_to_detail(monkeypatch):
    api = mock_api(monkeypatch)
    monkeypatch.setattr(
        streamlit, "dataframe",
        lambda *args, **kwargs: SimpleNamespace(selection=SimpleNamespace(rows=[0])),
    )
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "history"
    app.run(timeout=15)
    assert not app.button(key="open_report").disabled
    app.button(key="open_report").click().run()
    assert not app.exception
    assert app.title[0].value == "Szczegóły raportu"
    assert app.query_params["report_id"] == str(api.report.return_value.report_id)
    api.report.assert_called_once_with(str(api.report.return_value.report_id))


def test_invalid_report_link_does_not_call_api(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP))
    app.query_params.update(view="report", report_id="not-a-report-id")
    app.run(timeout=15)
    assert not app.exception
    assert "Niepoprawny identyfikator" in app.error[0].value
    api.report.assert_not_called()


@pytest.mark.parametrize("view", ["evaluation"])
def test_evaluation_shows_missing_results(monkeypatch, view):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP)).run(timeout=15)
    app.button(key=f"tile_{view}").click().run()
    assert not app.exception
    assert "Brak zapisanych wyników" in app.info[0].value
    assert not app.dataframe
    api.history.assert_not_called()


def test_report_can_return_to_analysis(monkeypatch):
    api = mock_api(monkeypatch)
    app = AppTest.from_file(str(APP))
    app.query_params.update(
        view="report", report_id=str(api.report.return_value.report_id), back="analysis",
    )
    app.run(timeout=15)
    app.button(key="back_from_report").click().run()
    assert not app.exception
    assert app.title[0].value == "Analiza logów"
    app.button(key="back_to_home").click().run()
    assert not app.exception
    assert app.title[0].value == "Analizator logów"
