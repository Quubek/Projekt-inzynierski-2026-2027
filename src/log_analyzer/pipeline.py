from collections import Counter
import os
from uuid import uuid4
from uuid import NAMESPACE_URL, uuid5

from log_analyzer.contracts import AnalysisResponse, AnalyzeRequest, Finding
from log_analyzer.parsing.parser import group_events, parse_logs
from log_analyzer.detection.rules import evaluate_hdfs
from log_analyzer.detection.model import (
    MODEL_VERSION,
    features_from_block,
    model_is_available,
    predict_features,
)


def _evaluate_model(events, groups, analysis_id: str):
    model_path = os.getenv("DETECTION_MODEL_PATH")
    if not model_path or not model_is_available(model_path):
        return groups, [], "not_configured", "Model ML nie jest dostępny. Umieść zgodny artefakt w models/baseline.joblib."

    events_by_id = {event.event_id: event for event in events}
    scored_groups = []
    findings = []
    skipped = 0
    for group in groups:
        members = [events_by_id[event_id] for event_id in group.event_ids]
        model_members = [event for event in members if event.block_ids and event.block_ids[0] == group.group_id]
        features = features_from_block(group.group_id, members)
        try:
            prediction = predict_features(features, model_path)
        except (OSError, ValueError, EOFError, ImportError, AttributeError):
            skipped += 1
            scored_groups.append(group)
            continue

        label = "anomaly" if prediction["is_anomaly"] else "normal"
        scored_groups.append(group.model_copy(update={
            "ml_prediction": label,
            "ml_score": prediction["score"],
            "model_version": prediction["model_version"],
        }))
        if prediction["is_anomaly"]:
            findings.append(Finding(
                finding_id=str(uuid5(NAMESPACE_URL, f"{analysis_id}:ml:{group.group_id}:{MODEL_VERSION}")),
                analysis_id=analysis_id,
                rule_ids=[],
                title="Predykcja modelu: anomalia w grupie HDFS",
                reason=(
                    f"Model {prediction['model_version']} ocenił grupę BlockID "
                    f"{group.group_id} jako anomalię (wynik {prediction['score']:.3f}). "
                    "To wynik klasyfikatora, który wymaga weryfikacji na logach źródłowych."
                ),
                source="ml",
                event_ids=[event.event_id for event in model_members],
                score=prediction["score"],
                model_version=prediction["model_version"],
                details={"group_id": group.group_id},
            ))

    if skipped:
        return scored_groups, findings, "partial", (
            f"Model nie ocenił {skipped} grup. Sprawdź dostępność i zgodność artefaktu "
            "oraz obecność cech rozpoznawanych przez jego słownik."
        )
    return scored_groups, findings, "completed", None


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
    detection_status = "not_configured"
    if request.log_format == "hdfs":
        findings = evaluate_hdfs(events, analysis_id)
        groups, model_findings, detection_status, model_warning = _evaluate_model(
            events, groups, analysis_id
        )
        findings.extend(model_findings)
        if model_warning:
            warnings.append(model_warning)
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
            warnings.append("Wskazania reguł i predykcje ML są sygnałami do sprawdzenia. Progi reguł są demonstracyjne, a wynik nie potwierdza awarii ani ataku.")
    else:
        warnings.append("SSH: grupowanie po hoście jest demonstracyjne. Reguły HDFS nie są stosowane do logów SSH, a model ML nie jest podłączony.")
    return AnalysisResponse(
        analysis_id=analysis_id, log_format=request.log_format, events=events,
        detection_status=detection_status,
        groups=groups, warnings=warnings, findings=findings,
        rules_status="completed" if request.log_format == "hdfs" else "unsupported",
        source_timezone=request.source_timezone, source_year=request.source_year, data_scope=request.data_scope,
        diagnostics=["Identyfikatory Drain3 są lokalne dla paczki. Nie są identyfikatorami cech modelu HD."],
    )
