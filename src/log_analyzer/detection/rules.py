"""Trzy wyjaśnialne reguły HDFS. Wskazania do sprawdzenia, bez potwierdzania ataku."""

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from log_analyzer.contracts import Finding, NormalizedEvent
from log_analyzer.detection.catalog import (
    EXCEPTION_BURST_COUNT, EXCEPTION_WINDOW_SECONDS, LARGE_DELETE_BLOCKS,
    RULE_NAMES, RULES_VERSION, rule_definition,
)


def _time(event: NormalizedEvent):
    if event.time_issue not in (None, "missing_timezone"):
        return None, "unknown"
    value = event.timestamp or event.timestamp_local
    return (datetime.fromisoformat(value), "utc" if event.timestamp else "source_local") if value else (None, "unknown")


def _finding(analysis_id, rule_ids, title, reason, events, node, priority, details=None):
    event_ids = list(dict.fromkeys(event.event_id for event in events))
    times = [_time(event) for event in events]
    bases = {basis for value, basis in times if value is not None}
    basis = next(iter(bases)) if len(bases) == 1 and all(value is not None for value, _ in times) else "unknown"
    values = [value for value, _ in times] if basis != "unknown" else []
    return Finding(
        finding_id=str(uuid5(NAMESPACE_URL, f"{analysis_id}:{','.join(rule_ids)}:{'|'.join(sorted(event_ids))}")),
        analysis_id=analysis_id, rule_ids=rule_ids, title=title, reason=reason,
        event_ids=event_ids, node=node, priority=priority,
        time_from=min(values).isoformat() if values else None,
        time_to=max(values).isoformat() if values else None, time_basis=basis,
        details=details or {},
        rules_version=RULES_VERSION,
        rule_definitions=[rule_definition(rule_id, details=details) for rule_id in rule_ids],
    )


def evaluate_hdfs(events: list[NormalizedEvent], analysis_id: str) -> list[Finding]:
    findings = []
    exceptions = defaultdict(list)
    for event in events:
        if event.event_type == "block_serving_exception":
            exceptions[event.parameters.get("node_ip")].append(event)
        if event.event_type == "block_delete_request" and len(event.block_ids) >= LARGE_DELETE_BLOCKS:
            findings.append(_finding(
                analysis_id, ["HDFS-003"], RULE_NAMES["HDFS-003"],
                f"Jedno polecenie obejmuje {len(event.block_ids)} bloków, przy demonstracyjnym progu {LARGE_DELETE_BLOCKS}. "
                "Może to być prawidłowa operacja utrzymaniowa; sprawdź jej kontekst.",
                [event], event.parameters.get("target_ip"), "low",
                {"block_count": len(event.block_ids), "threshold": LARGE_DELETE_BLOCKS},
            ))

    for node, node_events in exceptions.items():
        covered = set()
        if node is not None:
            for basis in ("utc", "source_local"):
                timed = sorted(
                    [(value, event) for event in node_events for value, kind in [_time(event)] if value is not None and kind == basis],
                    key=lambda pair: pair[0],
                )
                times = [value for value, _ in timed]
                index = 0
                while index < len(timed):
                    end = bisect_right(times, times[index] + timedelta(seconds=EXCEPTION_WINDOW_SECONDS))
                    if end - index >= EXCEPTION_BURST_COUNT:
                        members = [event for _, event in timed[index:end]]
                        findings.append(_finding(
                            analysis_id, ["HDFS-001", "HDFS-002"], RULE_NAMES["HDFS-002"],
                            f"Węzeł {node}: {len(members)} wyjątków w oknie {EXCEPTION_WINDOW_SECONDS // 60} minut "
                            f"w dostarczonych danych. Demonstracyjny próg: {EXCEPTION_BURST_COUNT}. "
                            "Wskazanie nie potwierdza awarii ani ataku.",
                            members, node, "medium",
                            {"observed_count": len(members), "threshold": EXCEPTION_BURST_COUNT, "window_seconds": EXCEPTION_WINDOW_SECONDS},
                        ))
                        covered.update(event.event_id for event in members)
                        index = end
                    else:
                        index += 1
        remaining = [event for event in node_events if event.event_id not in covered]
        if remaining:
            findings.append(_finding(
                analysis_id, ["HDFS-001"], RULE_NAMES["HDFS-001"],
                f"Zarejestrowano {len(remaining)} komunikatów o wyjątku podczas udostępniania bloku"
                + (f" dla węzła {node}. " if node else ". ")
                + "To sygnał do sprawdzenia. Przyczyna i wpływ nie wynikają z samego komunikatu.",
                remaining, node, "low", {"observed_count": len(remaining)},
            ))
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unassessed": 4}
    return sorted(findings, key=lambda item: (rank[item.priority], item.time_from or "", item.finding_id))
