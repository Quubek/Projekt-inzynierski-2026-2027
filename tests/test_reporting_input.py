import json

import pytest

from log_analyzer.contracts import AnalyzeRequest
from log_analyzer.pipeline import analyze
from log_analyzer.reporting.input import MAX_REPORT_INPUT_BYTES, prepare_report_input


def event(index, **extra):
    return {"event_id": f"event-{index}", "raw": f"source {index}", **extra}


def test_llm_input_does_not_repeat_templates_and_block_lists():
    raw = "BLOCK* ask 10.0.0.1:50010 to delete " + " ".join(f"blk_{10**18 + i}" for i in range(100))
    result = analyze(AnalyzeRequest(logs=[f"081109 203615 148 INFO dfs.FSNamesystem: {raw}"]))
    normalized = result.events[0].model_dump(mode="json")
    prepared = prepare_report_input([normalized])
    assert prepared.mode == "full"
    assert prepared.payload["events"][0]["raw"] == normalized["raw"]
    assert "template" not in prepared.payload["events"][0]
    assert "block_ids" not in prepared.payload["events"][0]
    assert len(json.dumps(prepared.payload, ensure_ascii=False, separators=(",", ":")).encode()) <= MAX_REPORT_INPUT_BYTES


def test_aggregation_counts_all_events_and_declares_missing_originals():
    events = [event(index, log_level="WARN" if index < 70 else "INFO", event_type="block_serving_exception") for index in range(100)]
    prepared = prepare_report_input(events)
    assert prepared.mode == "aggregated"
    assert prepared.payload["summary"]["levels"] == {"WARN": 70, "INFO": 30}
    assert prepared.payload["total_events"] == 100
    assert len(prepared.event_ids) <= 20
    assert len(prepared.event_ids) + prepared.payload["omitted_events"] == 100
    assert len(prepared.event_ids) == len(set(prepared.event_ids))
    assert len(json.dumps(prepared.payload, ensure_ascii=False, separators=(",", ":")).encode()) <= MAX_REPORT_INPUT_BYTES


def test_raw_source_is_never_silently_truncated():
    events = [event(1, raw="x" * 10000)]
    with pytest.raises(ValueError, match="Nie przycięto"):
        prepare_report_input(events)
    assert len(events[0]["raw"]) == 10000
