import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import streamlit
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app as api_app
from log_analyzer.contracts import MAX_LOG_LINES, AnalyzeRequest
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.analysis import MAX_INPUT_BYTES, decode_log_file, prepare_request
from log_analyzer.dashboard.api_client import ReportsApi, ReportsApiError
from log_analyzer.pipeline import analyze


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/log_analyzer/dashboard/app.py"


def sample(log_format="ssh"):
    return json.loads((ROOT / f"data/samples/{log_format}_request.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("log_format", ["ssh", "hdfs"])
def test_dashboard_client_uses_existing_analysis_endpoint(log_format):
    backend = TestClient(api_app)

    def respond(request):
        assert request.method == "POST" and request.url.path == "/api/v1/analyze"
        response = backend.post(request.url.path, json=json.loads(request.content))
        return httpx.Response(response.status_code, json=response.json())

    payload = sample(log_format)
    request = prepare_request("\n".join(payload["logs"]), log_format)
    with ReportsApi("http://testserver", transport=httpx.MockTransport(respond)) as client:
        result = client.analyze(request)
    assert len(result.events) == len(payload["logs"])
    assert result.events[0].raw == payload["logs"][0]
    assert result.detection_status == "not_configured"
    assert result.reporting_status == "not_run"


@pytest.mark.parametrize("text,log_format,message", [
    (" \n\n", "ssh", "Wklej logi"),
    ("x\n" * (MAX_LOG_LINES + 1), "ssh", str(MAX_LOG_LINES)),
    ("x" * 10001, "ssh", "10 000"),
    ("x", "unsupported", "format"),
    ("x" * (MAX_INPUT_BYTES + 1), "ssh", "2 MB"),
])
def test_input_validation(text, log_format, message):
    with pytest.raises(ValueError, match=message):
        prepare_request(text, log_format)


def test_utf8_bom_blank_lines_and_source_content():
    original = sample()["logs"][0]
    text = decode_log_file(("\ufeff\n" + original + "\n\n").encode("utf-8"))
    request = prepare_request(text, "ssh")
    assert request.logs == [original]


def test_upload_limit_is_shared_with_api_and_accepts_two_thousand_lines():
    line = sample("hdfs")["logs"][0]
    for count in (2000, MAX_LOG_LINES):
        request = prepare_request("\n".join([line] * count), "hdfs")
        assert len(request.logs) == count
    with pytest.raises(ValueError):
        AnalyzeRequest(logs=[line] * (MAX_LOG_LINES + 1), log_format="hdfs")


@pytest.mark.parametrize("content,message", [
    (b"\xff\xfe", "UTF-8"), (b"x" * (MAX_INPUT_BYTES + 1), "2 MB"),
])
def test_invalid_file(content, message):
    with pytest.raises(ValueError, match=message):
        decode_log_file(content)


def test_backend_parser_error_is_shown_to_user():
    backend = TestClient(api_app)

    def respond(request):
        response = backend.post(request.url.path, json=json.loads(request.content))
        return httpx.Response(response.status_code, json=response.json())

    with ReportsApi("http://testserver", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ReportsApiError, match="Wpis 1"):
            client.analyze(prepare_request("not an SSH log", "ssh"))


def mock_analysis_api(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.analyze.return_value = analyze(AnalyzeRequest.model_validate(sample()))
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: client)
    return client


def analysis_page():
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params["view"] = "analysis"
    return page.run(timeout=15)


def test_analysis_form_sends_logs_and_shows_parsing_only(monkeypatch):
    client = mock_analysis_api(monkeypatch)
    page = analysis_page()
    assert not page.exception
    client.analyze.assert_not_called()
    page.text_area(key="analysis_text").set_value("\n".join(sample()["logs"]))
    page.button(key="submit_analysis").click().run()
    assert not page.exception
    assert client.analyze.call_args.args[0].logs == sample()["logs"]
    assert len(page.dataframe) == 2
    assert any("nie rozstrzyga" in item.value for item in page.info)
    assert not page.get("download_button")
    client.report.assert_not_called()
    page.button(key="back_to_home").click().run()
    page.button(key="tile_analysis").click().run()
    assert not page.exception and len(page.dataframe) == 2
    assert client.analyze.call_count == 1


def test_empty_input_never_calls_api(monkeypatch):
    client = mock_analysis_api(monkeypatch)
    page = analysis_page()
    page.button(key="submit_analysis").click().run()
    assert not page.exception
    assert "Wklej logi" in page.error[0].value
    assert not page.dataframe
    client.analyze.assert_not_called()


def test_failed_new_request_clears_old_result(monkeypatch):
    client = mock_analysis_api(monkeypatch)
    page = analysis_page()
    page.text_area(key="analysis_text").set_value("\n".join(sample()["logs"]))
    page.button(key="submit_analysis").click().run()
    assert page.dataframe
    client.analyze.side_effect = ReportsApiError("Nie można połączyć się z API.")
    page.button(key="submit_analysis").click().run()
    assert not page.exception
    assert "połączyć" in page.error[0].value
    assert not page.dataframe


def test_file_mode_uses_same_request_contract(monkeypatch):
    client = mock_analysis_api(monkeypatch)
    content = "\n".join(sample()["logs"]).encode("utf-8")
    upload = MagicMock()
    upload.getvalue.return_value = content
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: upload)
    page = analysis_page()
    page.radio(key="analysis_input_mode").set_value("Prześlij plik").run()
    page.button(key="submit_analysis").click().run()
    assert not page.exception
    assert client.analyze.call_args.args[0].logs == sample()["logs"]
