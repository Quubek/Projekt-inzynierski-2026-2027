"""Połączenie zapisanej analizy z generatorem JF; bez decyzji o anomalii."""

from log_analyzer.contracts import AnalysisResponse, Finding, RaportZdarzen
from log_analyzer.reporting.ollama_klient import generuj_raport
from log_analyzer.storage import sqlite_repo


def generate_group_report(analysis: AnalysisResponse, group_id: str) -> RaportZdarzen:
    group = next((item for item in analysis.groups if item.group_id == group_id), None)
    if group is None:
        raise ValueError("Wybrana grupa nie należy do tej analizy.")
    return _generate(analysis, group.event_ids, group_id=group.group_id)


def generate_finding_report(analysis: AnalysisResponse, finding_id: str) -> RaportZdarzen:
    finding = next((item for item in analysis.findings if item.finding_id == finding_id), None)
    if finding is None:
        raise ValueError("Wybrane wykrycie nie należy do tej analizy.")
    return _generate(analysis, finding.event_ids, finding=finding)


def _generate(analysis, event_ids, *, group_id=None, finding: Finding | None = None):
    events = {event.event_id: event for event in analysis.events}
    if not event_ids or any(event_id not in events for event_id in event_ids):
        raise ValueError("Brak poprawnego zestawu zdarzeń źródłowych.")
    context = {"data_scope": analysis.data_scope, "source_timezone": analysis.source_timezone}
    if finding:
        context["finding"] = finding.model_dump(mode="json", exclude={"event_ids", "finding_id", "analysis_id"})
    report = generuj_raport([events[event_id].model_dump(mode="json") for event_id in event_ids], context=context)
    report.analysis_id = analysis.analysis_id
    report.group_id = group_id
    report.finding = finding
    sqlite_repo.inicjalizuj_baze()
    sqlite_repo.zapisz_raport(report.model_dump_json())
    return report
