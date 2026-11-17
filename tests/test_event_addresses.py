from pathlib import Path
from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from log_analyzer.api.main import app
from log_analyzer.contracts import AnalyzeRequest, NormalizedEvent
from log_analyzer.dashboard.analysis import event_address_columns
from log_analyzer.parsing.addresses import addresses_for_event, find_ips
from log_analyzer.pipeline import analyze
from test_hdfs_rules import line


@pytest.mark.parametrize("message,expected", [
    ("Receiving block blk_1 src: /10.0.0.1:1234 dest: /10.0.0.2:50010",
     {"source_ip": "10.0.0.1", "destination_ip": "10.0.0.2"}),
    ("Received block blk_1 of size 100 from /10.0.0.1", {"source_ip": "10.0.0.1"}),
    ("10.0.0.1:50010:Got exception while serving blk_1 to /10.0.0.2:",
     {"source_ip": "10.0.0.1", "node_ip": "10.0.0.1", "destination_ip": "10.0.0.2"}),
    ("10.0.0.1:50010 Served block blk_1 to /10.0.0.2",
     {"source_ip": "10.0.0.1", "node_ip": "10.0.0.1", "destination_ip": "10.0.0.2"}),
    ("10.0.0.1:50010 Starting thread to transfer block blk_1 to 10.0.0.2:50010",
     {"source_ip": "10.0.0.1", "node_ip": "10.0.0.1", "destination_ip": "10.0.0.2"}),
    ("BLOCK* ask 10.0.0.3:50010 to delete blk_1", {"target_ip": "10.0.0.3"}),
    ("BLOCK* NameSystem.addStoredBlock: blockMap updated: 10.0.0.3:50010 is added to blk_1 size 100",
     {"node_ip": "10.0.0.3"}),
    ("Unrecognized operation involving 10.0.0.4", {"other_ips": ["10.0.0.4"]}),
    ("Unrecognized operation involving 999.0.0.4", {}),
])
def test_parser_preserves_address_roles_without_guessing(message, expected):
    event = analyze(AnalyzeRequest(logs=[line(message)])).events[0]
    actual = {key: getattr(event, key) for key in
              ("source_ip", "destination_ip", "node_ip", "target_ip", "other_ips")}
    assert actual == {"source_ip": None, "destination_ip": None, "node_ip": None,
                      "target_ip": None, "other_ips": [], **expected}


def test_ssh_ipv6_and_destination_require_explicit_ip_host():
    message = "Failed password for admin from 2001:db8::1 port 1234 ssh2"
    for host, destination in (("server01", None), ("192.0.2.20", "192.0.2.20")):
        event = analyze(AnalyzeRequest(logs=[f"Nov 4 10:14:03 {host} sshd[1]: {message}"], log_format="ssh")).events[0]
        assert event.source_ip == "2001:db8::1"
        assert event.destination_ip == destination
        assert event.other_ips == []
    ips = find_ips("peer [::ffff:192.0.2.1]:1234 and 999.0.0.1")
    assert len(ips) == 1 and ip_address(ips[0]) == ip_address("::ffff:192.0.2.1")


def test_old_analysis_can_show_roles_without_rewriting_original_data():
    event = analyze(AnalyzeRequest(logs=[line("BLOCK* ask 10.0.0.3:50010 to delete blk_1")])).events[0]
    legacy = event.model_dump(exclude={"source_ip", "destination_ip", "node_ip", "target_ip", "other_ips"})
    loaded = NormalizedEvent.model_validate(legacy)
    assert loaded.target_ip is None
    assert addresses_for_event(loaded)["target_ip"] == "10.0.0.3"
    assert event_address_columns(loaded) == {"IP źródłowe": "Nie ustalono",
                                            "IP docelowe": "Nie ustalono", "Pozostałe IP": "10.0.0.3"}
    assert loaded.target_ip is None


def test_api_stores_new_address_fields():
    client = TestClient(app)
    response = client.post("/api/v1/analyze", json={"logs": [line(
        "Receiving block blk_1 src: /10.0.0.1:1234 dest: /10.0.0.2:50010")]})
    assert response.status_code == 200
    saved = client.get("/api/v1/analyses/" + response.json()["analysis_id"]).json()
    assert saved["events"][0]["source_ip"] == "10.0.0.1"
    assert saved["events"][0]["destination_ip"] == "10.0.0.2"


def test_dashboard_address_filters_combine_and_include_command_targets():
    result = analyze(AnalyzeRequest(logs=[
        line("Receiving block blk_1 src: /10.0.0.1:1234 dest: /10.0.0.2:50010"),
        line("BLOCK* ask 10.0.0.3:50010 to delete blk_2"),
        line("Deleting block blk_3 file /tmp/blk_3"),
    ]))
    path = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"
    page = AppTest.from_file(str(path), default_timeout=15)
    page.query_params["view"] = "analysis"
    page.session_state["analysis_result"] = result.model_dump(mode="json")
    page.run()
    assert not page.exception and len(page.dataframe[0].value) == 3
    prefix = result.analysis_id
    page.selectbox(key=f"source_ip_{prefix}").set_value("10.0.0.1").run()
    assert len(page.dataframe[0].value) == 1
    page.selectbox(key=f"any_ip_{prefix}").set_value("10.0.0.3").run()
    assert len(page.dataframe[0].value) == 0
    page.selectbox(key=f"source_ip_{prefix}").set_value("unknown").run()
    assert list(page.dataframe[0].value["Pozostałe IP"]) == ["10.0.0.3"]
    page.selectbox(key=f"any_ip_{prefix}").set_value("unknown").run()
    assert len(page.dataframe[0].value) == 1
    assert list(page.dataframe[0].value["Nr wpisu"]) == [3]
    assert not page.exception
