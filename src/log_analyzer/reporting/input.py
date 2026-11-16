"""Ograniczone wejście LLM z jawną informacją o agregacji i źródłach."""

import json
from collections import Counter
from dataclasses import dataclass

MAX_REPORT_EVENTS = 20
MAX_REPORT_INPUT_BYTES = 6000


@dataclass(frozen=True)
class PreparedReportInput:
    payload: dict
    event_ids: list[str]
    mode: str


def _size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def prepare_report_input(events: list[dict], context: dict | None = None) -> PreparedReportInput:
    if not events:
        raise ValueError("Lista zdarzeń jest pusta.")
    minimal = [{
        "event_id": event["event_id"], "raw": event["raw"], "host": event.get("host"),
        "timestamp_utc": event.get("timestamp"),
        "czas_zrodlowy": event.get("timestamp_local") or event.get("timestamp_raw"),
    } for event in events]
    payload = {"mode": "full", "total_events": len(events), "omitted_events": 0,
               "context": context or {}, "events": minimal}
    if len(events) <= MAX_REPORT_EVENTS and _size(payload) <= MAX_REPORT_INPUT_BYTES:
        return PreparedReportInput(payload, [event["event_id"] for event in events], "full")

    # Agregaty obejmują wszystkie źródła. Oryginalne logi pozostają w raporcie i SQLite.
    payload.update(mode="aggregated", events=[], omitted_events=len(events), summary={
        "levels": dict(Counter(event.get("log_level") or "unknown" for event in events)),
        "event_types": dict(Counter(event.get("event_type") or "other" for event in events)),
        "components_top_10": dict(Counter(event.get("component") or "unknown" for event in events).most_common(10)),
        "events_without_utc": sum(not event.get("timestamp") for event in events),
    })
    if _size(payload) > MAX_REPORT_INPUT_BYTES:
        raise ValueError("Metadane raportu przekraczają limit wejścia LLM. Nie przycięto źródeł.")
    representative = {}
    for index, event in enumerate(events):
        representative.setdefault((event.get("event_type"), event.get("log_level")), index)
    important = [i for i, event in enumerate(events) if event.get("log_level") in ("ERROR", "FATAL", "WARN")]
    candidates = dict.fromkeys([0, len(events) - 1, *important, *representative.values(), *range(len(events))])
    selected = []
    for index in candidates:
        if len(selected) >= MAX_REPORT_EVENTS:
            break
        proposed = sorted([*selected, index])
        payload["events"] = [minimal[i] for i in proposed]
        payload["omitted_events"] = len(events) - len(proposed)
        if _size(payload) <= MAX_REPORT_INPUT_BYTES:
            selected = proposed
    payload["events"] = [minimal[i] for i in selected]
    payload["omitted_events"] = len(events) - len(selected)
    if not selected:
        raise ValueError("Pojedyncze wpisy są za długie dla wejścia LLM. Nie przycięto oryginalnych logów.")
    return PreparedReportInput(payload, [minimal[i]["event_id"] for i in selected], "aggregated")
