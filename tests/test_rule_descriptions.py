from pathlib import Path
from unittest.mock import MagicMock

from streamlit.testing.v1 import AppTest

from log_analyzer.contracts import AnalyzeRequest, Finding
from log_analyzer.dashboard import api_client
from log_analyzer.detection import catalog
from log_analyzer.pipeline import analyze
from test_report_history import make_report


def deletion_finding():
    blocks = " ".join(f"blk_{index}" for index in range(50))
    result = analyze(AnalyzeRequest(logs=[f"081109 203615 148 INFO dfs.FSNamesystem: BLOCK* ask 10.0.0.1:50010 to delete {blocks}"]))
    return result.findings[0]


def test_historical_report_tooltip_uses_saved_rule_description(monkeypatch):
    finding = Finding.model_validate_json(deletion_finding().model_dump_json())
    monkeypatch.setattr(catalog, "LARGE_DELETE_BLOCKS", 999)
    report = make_report(1, "2026-11-16T10:00:00Z", None)
    report.finding = finding
    report.event_ids = finding.event_ids
    client = MagicMock()
    client.__enter__.return_value = client
    client.report.return_value = report
    monkeypatch.setattr(api_client, "ReportsApi", lambda url: client)
    path = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"
    page = AppTest.from_file(str(path), default_timeout=15)
    page.query_params.update(view="report", report_id=str(report.report_id))
    page.run()
    assert not page.exception
    tooltip = page.get("popover")[0].proto.popover
    assert tooltip.label == "Żądanie usunięcia wielu bloków"
    assert "50" in tooltip.help and "999" not in tooltip.help
    assert any(finding.rule_definitions[0].description == item.value for item in page.text)


def test_legacy_finding_uses_recorded_threshold_without_rewriting_it(monkeypatch):
    saved = deletion_finding().model_dump(mode="json", exclude={"rule_definitions"})
    legacy = Finding.model_validate(saved)
    monkeypatch.setattr(catalog, "LARGE_DELETE_BLOCKS", 999)
    description = catalog.finding_rules(legacy)[0].description
    assert "50" in description and "999" not in description
    assert legacy.details["threshold"] == 50
