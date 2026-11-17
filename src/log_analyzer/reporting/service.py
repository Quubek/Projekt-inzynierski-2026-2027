"""Połączenie zapisanej analizy z generatorem JF; bez decyzji o anomalii."""

from log_analyzer.contracts import AnalysisResponse, Finding, RaportZdarzen
from log_analyzer.reporting.ollama_klient import generuj_raport
from log_analyzer.storage import sqlite_repo


def generate_group_report(analysis: AnalysisResponse, group_id: str) -> RaportZdarzen:
    return generate_groups_report(analysis, [group_id])


def generate_groups_report(analysis: AnalysisResponse, group_ids: list[str]) -> RaportZdarzen:
    selected = set(group_ids)
    groups = [group for group in analysis.groups if group.group_id in selected]
    if not selected or len(groups) != len(selected):
        raise ValueError("Wybrana grupa nie należy do tej analizy.")
    event_ids = {event_id for group in groups for event_id in group.event_ids}
    # Jedno źródło tylko raz, w kolejności oryginalnej analizy.
    ordered_ids = [event.event_id for event in analysis.events if event.event_id in event_ids]
    if len(ordered_ids) != len(event_ids):
        raise ValueError("Brak poprawnego zestawu zdarzeń źródłowych.")
    return _generate(analysis, ordered_ids, group_ids=[group.group_id for group in groups])


def generate_finding_report(analysis: AnalysisResponse, finding_id: str) -> RaportZdarzen:
    finding = next((item for item in analysis.findings if item.finding_id == finding_id), None)
    if finding is None:
        raise ValueError("Wybrane wykrycie nie należy do tej analizy.")
    return _generate(analysis, finding.event_ids, finding=finding)


def _generate(analysis, event_ids, *, group_ids=None, finding: Finding | None = None):
    events = {event.event_id: event for event in analysis.events}
    if not event_ids or any(event_id not in events for event_id in event_ids):
        raise ValueError("Brak poprawnego zestawu zdarzeń źródłowych.")
    context = {"data_scope": analysis.data_scope, "source_timezone": analysis.source_timezone}
    if group_ids:
        context["manual_selection"] = {
            "group_count": len(group_ids), "group_ids_preview": group_ids[:10],
            "omitted_group_ids": max(0, len(group_ids) - 10),
            "related_incident_confirmed": False,
        }
    if finding:
        context["finding"] = finding.model_dump(mode="json", exclude={"event_ids", "finding_id", "analysis_id"})
    report = generuj_raport([events[event_id].model_dump(mode="json") for event_id in event_ids], context=context)
    report.analysis_id = analysis.analysis_id
    report.group_ids = group_ids or []
    report.group_id = group_ids[0] if group_ids and len(group_ids) == 1 else None
    report.finding = finding
    sqlite_repo.inicjalizuj_baze()
    sqlite_repo.zapisz_raport(report.model_dump_json())
    return report
