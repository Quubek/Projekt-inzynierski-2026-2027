from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from log_analyzer.api.main import app
from log_analyzer.contracts import MAX_LOG_LINES
from log_analyzer.parsing import file_input
from log_analyzer.parsing.file_input import FileTooLarge, LogFileReader, LogImportError, MAX_FILE_BYTES
from log_analyzer.storage import sqlite_repo


CLIENT = TestClient(app)
LINE = "2026-11-17T10:00:00Z server01 sshd[1]: Failed password for admin from 192.0.2.1 port 1234 ssh2"


def upload(chunks, **params):
    return CLIENT.post("/api/v1/analyze/file", params={"log_format": "ssh", **params},
                       content=chunks, headers={"Content-Type": "application/octet-stream"})


def test_utf8_bom_crlf_and_multibyte_characters_across_arbitrary_chunk_boundaries():
    content = ("\ufeff\r\n" + LINE + " użytkownik\r\n\t\n" + LINE + "\r").encode("utf-8")
    reader = LogFileReader()
    for byte in content:
        reader.feed(bytes([byte]))
    assert reader.finish() == [LINE + " użytkownik", LINE]


def test_exact_two_gib_boundary_does_not_require_allocating_two_gib():
    assert MAX_FILE_BYTES == 2 * 1024**3
    LogFileReader.check_size(MAX_FILE_BYTES)
    with pytest.raises(FileTooLarge, match="2 GB"):
        LogFileReader.check_size(MAX_FILE_BYTES + 1)


def test_streaming_byte_limit_is_enforced_without_content_length(monkeypatch):
    monkeypatch.setattr(file_input, "MAX_FILE_BYTES", len(LINE.encode("utf-8")))
    response = upload(iter([LINE.encode(), b"\n"]))
    assert response.status_code == 413 and "2 GB" in response.json()["detail"]
    assert not sqlite_repo.SCIEZKA_BAZY.exists()


def test_declared_oversized_file_is_rejected_before_body_is_read():
    consumed = []

    def chunks():
        consumed.append(True)
        yield b"not read"

    response = CLIENT.post("/api/v1/analyze/file", content=chunks(),
                           headers={"Content-Length": str(MAX_FILE_BYTES + 1)})
    assert response.status_code == 413 and not consumed
    assert not sqlite_repo.SCIEZKA_BAZY.exists()


def test_import_accepts_ten_thousand_lines_and_preserves_sources():
    response = upload(iter([(LINE + "\n").encode()] * MAX_LOG_LINES))
    assert response.status_code == 200
    result = response.json()
    UUID(result["analysis_id"])
    assert result["event_count"] == 10000
    assert "events" not in result  # upload zwraca małe potwierdzenie, nie kopię całej analizy
    saved = CLIENT.get("/api/v1/analyses/" + result["analysis_id"]).json()
    assert len(saved["events"]) == 10000
    assert saved["events"][0]["raw"] == saved["events"][-1]["raw"] == LINE


def test_import_above_previous_two_mb_limit_uses_same_pipeline_and_source_options():
    line = LINE + " " + "a" * 1100
    content = ((line + "\n") * 2000).encode()
    assert len(content) > 2 * 1024**2
    response = upload((content[i:i + 65536] for i in range(0, len(content), 65536)),
                      source_timezone="Europe/Warsaw", data_scope="sample")
    assert response.status_code == 200 and response.json()["event_count"] == 2000
    saved = CLIENT.get("/api/v1/analyses/" + response.json()["analysis_id"]).json()
    assert saved["data_scope"] == "sample" and saved["source_timezone"] == "Europe/Warsaw"
    assert saved["events"][0]["timezone_source"] == "log"


@pytest.mark.parametrize("content,message", [
    (b"", "niepustych"),
    (b"\n\t\r\n ", "niepustych"),
    (b"\xff\xfe", "UTF-8"),
    (b"\xc5", "UTF-8"),
    (b"x" * 10001, "10 000"),
    ((LINE + "\n").encode() * (MAX_LOG_LINES + 1), str(MAX_LOG_LINES)),
    (b"not an SSH log", "Wpis 1"),
])
def test_invalid_import_never_saves_partial_analysis(content, message):
    response = upload(iter([content]))
    assert response.status_code == 422 and message in response.json()["detail"]
    assert not sqlite_repo.SCIEZKA_BAZY.exists()


def test_long_unterminated_line_is_rejected_before_reading_remainder():
    reader = LogFileReader()
    reader.feed(b"x" * 10000)
    with pytest.raises(LogImportError, match="10 000"):
        reader.feed(b"x")


def test_blank_chunks_do_not_accumulate_or_count_as_events():
    reader = LogFileReader()
    for _ in range(100):
        reader.feed(b" " * 65536)
    reader.feed(("\n" + LINE).encode())
    assert reader.finish() == [LINE]


@pytest.mark.parametrize("params", [{"source_timezone": "invalid/zone"}, {"source_year": 1800},
                                     {"log_format": "unknown"}, {"data_scope": "invalid"}])
def test_invalid_source_options_are_rejected_without_saving(params):
    assert upload(iter([LINE.encode()]), **params).status_code == 422
    assert not sqlite_repo.SCIEZKA_BAZY.exists()


def test_import_form_uses_browser_public_dashboard_url_and_raw_file_upload(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "http://localhost:8501")
    response = CLIENT.get("/import")
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]
    assert str(MAX_FILE_BYTES) in response.text and "10000" in response.text
    assert "__DASHBOARD_URL__" not in response.text
    assert '"http://localhost:8501"' in response.text
    assert "xhr.send(file)" in response.text and "FileReader" not in response.text
