from collections import Counter
from uuid import uuid4

from log_analyzer.contracts import AnalysisResponse, AnalyzeRequest
from log_analyzer.parsing.parser import group_events, parse_logs
from log_analyzer.detection.rules import evaluate_hdfs


def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    analysis_id = str(uuid4())
    events = parse_logs(
        request.logs, request.log_format, analysis_id,
        source_timezone=request.source_timezone, source_year=request.source_year,
    )
    groups = group_events(events, request.log_format)
    warnings = []
    issues = Counter(event.time_issue for event in events if event.time_issue)
    if issues["missing_timezone"]:
        warnings.append(f"W {issues['missing_timezone']} wpisach jest data i godzina, ale nie określono strefy czasowej. Pokazujemy czas źródłowy bez przeliczania na UTC.")
    if issues["missing_year"]:
        warnings.append(f"W {issues['missing_year']} wpisach brakuje roku. Nie przypisano automatycznie bieżącego roku; rok źródła można podać przy imporcie.")
    dst_issues = issues["ambiguous_local_time"] + issues["nonexistent_local_time"]
    if dst_issues:
        warnings.append(f"W {dst_issues} wpisach czas lokalny jest niejednoznaczny lub nie istnieje w podanej strefie podczas zmiany czasu. Nie wyznaczono dla nich UTC.")
    missing_hosts = sum(event.host is None for event in events)
    if missing_hosts:
        warnings.append(f"Nie ustalono hosta źródłowego dla {missing_hosts} wpisów. Adresy w treści opisują uczestniczące węzły i nie zastępują hosta źródłowego.")
    findings = []
    if request.log_format == "hdfs":
        findings = evaluate_hdfs(events, analysis_id)
        without_block = sum(not event.block_ids for event in events)
        if without_block:
            warnings.append(f"W {without_block} wpisach nie znaleziono BlockID. Są widoczne w zdarzeniach, ale nie tworzą grup HDFS.")
        multiple = sum(len(event.block_ids) > 1 for event in events)
        if multiple:
            warnings.append(f"{multiple} wpisów dotyczy wielu bloków. Liczba grup BlockID nie oznacza liczby wykryć ani incydentów.")
        single = sum(len(group.event_ids) == 1 for group in groups)
        if request.data_scope != "complete":
            warnings.append(f"Kompletność sekwencji nie jest potwierdzona. {single} z {len(groups)} grup BlockID zawiera tylko jeden wpis. Nie oceniono brakujących zakończeń ani kolejności pełnych operacji.")
        if findings:
            warnings.append("Wskazania reguł i ich priorytety są wstępne. Progi demonstracyjne wymagają walidacji; wynik nie potwierdza awarii ani ataku.")
    else:
        warnings.append("SSH: grupowanie po hoście jest demonstracyjne. Reguły HDFS nie są stosowane do logów SSH, a model ML nie jest podłączony.")
    return AnalysisResponse(
        analysis_id=analysis_id, log_format=request.log_format, events=events,
        groups=groups, warnings=warnings, findings=findings,
        rules_status="completed" if request.log_format == "hdfs" else "unsupported",
        source_timezone=request.source_timezone, source_year=request.source_year, data_scope=request.data_scope,
        diagnostics=["Identyfikatory Drain3 są lokalne dla paczki. Nie są identyfikatorami cech modelu HD."],
    )
