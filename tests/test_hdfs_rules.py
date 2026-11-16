from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from log_analyzer.api.main import app
from log_analyzer.contracts import AnalyzeRequest
from log_analyzer.pipeline import analyze


def line(message, *, clock="203615", date="081109", level="INFO", component="dfs.DataNode$DataXceiver"):
    return f"{date} {clock} 148 {level} {component}: {message}"


def exception(index=0, *, node="10.0.0.1", seconds=0):
    clock = (datetime(2008, 11, 9, 20, 36, 15) + timedelta(seconds=seconds)).strftime("%H%M%S")
    return line(f"{node}:50010:Got exception while serving blk_{index} to /10.0.0.2:", clock=clock, level="WARN")


def run(lines, **options):
    return analyze(AnalyzeRequest(logs=lines, log_format="hdfs", **options))


def test_hdfs_preserves_local_time_and_creates_data_specific_warnings():
    result = run([line("Received block blk_1 of size 100 from /10.0.0.2")], data_scope="sample")
    event = result.events[0]
    assert event.timestamp is None and event.timestamp_local == "2008-11-09T20:36:15"
    assert event.log_level == "INFO" and event.event_type == "block_received"
    assert event.parameters["peer_ip"] == "10.0.0.2" and event.host is None
    assert any("jest data i godzina" in text for text in result.warnings)
    assert any("1 z 1 grup" in text for text in result.warnings)
    assert all("Drain3" not in text for text in result.warnings)


def test_configured_timezone_converts_to_utc_without_missing_zone_warning():
    result = run([line("Received block blk_1 of size 100 from /10.0.0.2")], source_timezone="Europe/Warsaw")
    event = result.events[0]
    assert event.timestamp == "2008-11-09T19:36:15+00:00"
    assert event.timezone_source == "configuration" and event.time_issue is None
    assert not any("nie określono strefy" in text for text in result.warnings)


def test_explicit_offset_takes_precedence_over_configuration():
    result = run([line("Received block blk_1", clock="203615+02:00")], source_timezone="UTC")
    assert result.events[0].timestamp == "2008-11-09T18:36:15+00:00"
    assert result.events[0].timezone_source == "log"


@pytest.mark.parametrize("date,issue", [("261025", "ambiguous_local_time"), ("260329", "nonexistent_local_time")])
def test_dst_ambiguity_is_reported_instead_of_guessing(date, issue):
    result = run([line("Received block blk_1", date=date, clock="023000")], source_timezone="Europe/Warsaw")
    assert result.events[0].timestamp is None
    assert result.events[0].time_issue == issue
    assert any("zmiany czasu" in text for text in result.warnings)


def test_ssh_year_is_only_added_when_provided():
    raw = "Nov 4 10:14:03 server01 sshd[1234]: Failed password for admin from 192.0.2.10 port 51234 ssh2"
    unknown = analyze(AnalyzeRequest(logs=[raw], log_format="ssh", source_timezone="UTC"))
    known = analyze(AnalyzeRequest(logs=[raw], log_format="ssh", source_timezone="UTC", source_year=2026))
    assert unknown.events[0].timestamp is None and unknown.events[0].time_issue == "missing_year"
    assert known.events[0].timestamp == "2026-11-04T10:14:03+00:00"


def test_ssh_iso_timestamp_with_zone_is_supported():
    raw = "2026-11-16T10:14:03+01:00 server01 sshd[1234]: Failed password for admin from 192.0.2.10 port 51234 ssh2"
    result = analyze(AnalyzeRequest(logs=[raw], log_format="ssh"))
    assert result.events[0].timestamp == "2026-11-16T09:14:03+00:00"
    assert result.events[0].timezone_source == "log"


def test_invalid_timezone_is_rejected_by_api():
    response = TestClient(app).post("/api/v1/analyze", json={"logs": [line("Received block blk_1")], "source_timezone": "Moon/Invalid"})
    assert response.status_code == 422


def test_normal_termination_and_deletion_do_not_trigger_rules():
    result = run([line("PacketResponder 1 for block blk_1 terminating"), line("Deleting block blk_2 file /tmp/blk_2")])
    assert result.findings == []
    assert result.events[0].event_type == "responder_finished"


def test_exception_has_evidence_and_correct_node_role():
    result = run([exception()])
    finding = result.findings[0]
    assert finding.rule_ids == ["HDFS-001"]
    assert finding.node == "10.0.0.1" and finding.node != result.events[0].parameters["peer_ip"]
    assert finding.event_ids == [result.events[0].event_id]
    assert finding.score is None and finding.priority_is_provisional
    assert finding.time_basis == "source_local"


def test_exception_burst_combines_rules_without_duplicate_evidence():
    result = run([exception(index, seconds=index * 30) for index in range(3)])
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.rule_ids == ["HDFS-001", "HDFS-002"]
    assert len(finding.event_ids) == 3 and finding.priority == "medium"


def test_burst_does_not_combine_different_nodes_or_exceed_window():
    result = run([exception(0), exception(1, node="10.0.0.3"), exception(2, seconds=301)])
    assert all("HDFS-002" not in finding.rule_ids for finding in result.findings)


def test_sliding_window_detects_burst_after_an_isolated_first_event():
    result = run([exception(i, seconds=seconds) for i, seconds in enumerate([0, 250, 350, 400])])
    bursts = [f for f in result.findings if "HDFS-002" in f.rule_ids]
    assert len(bursts) == 1 and len(bursts[0].event_ids) == 3
    all_ids = [eid for finding in result.findings for eid in finding.event_ids]
    assert len(all_ids) == len(set(all_ids)) == 4


def test_one_hundred_blocks_create_one_finding_not_one_hundred_alerts():
    message = "BLOCK* ask 10.0.0.1:50010 to delete " + " ".join(f"blk_{index}" for index in range(100))
    result = run([line(message)])
    assert len(result.groups) == 100 and len(result.findings) == 1
    assert result.findings[0].rule_ids == ["HDFS-003"]
    assert result.findings[0].details["block_count"] == 100
    assert len(result.findings[0].event_ids) == 1


def test_findings_persist_and_api_filters_them():
    backend = TestClient(app)
    result = backend.post("/api/v1/analyze", json={"logs": [exception()], "log_format": "hdfs"}).json()
    finding = result["findings"][0]
    assert backend.get(f"/api/v1/findings/{finding['finding_id']}").json() == finding
    response = backend.get("/api/v1/findings", params={"analysis_id": result["analysis_id"], "rule_id": "HDFS-001", "query": "10.0.0.1"}).json()
    assert response["total"] == 1 and response["findings"][0] == finding
    assert backend.get("/api/v1/findings?priority=critical").json()["total"] == 0
    assert backend.get("/api/v1/findings?rule_id=HDFS-00").json()["total"] == 0
