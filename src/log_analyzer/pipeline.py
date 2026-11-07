from uuid import uuid4

from log_analyzer.contracts import AnalysisResponse, AnalyzeRequest
from log_analyzer.parsing.parser import group_events, parse_logs


def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    analysis_id = str(uuid4())
    events = parse_logs(request.logs, request.log_format, analysis_id)
    warnings = [
        "Model HD nie jest podlaczony. Wynik nie stanowi detekcji anomalii.",
        "Raportowanie JF nie zostalo uruchomione.",
        "Brak strefy czasowej w logach: timestamp pozostaje null, czas zrodla jest w timestamp_raw.",
        "Identyfikatory Drain3 sa lokalne dla paczki i nie sa identyfikatorami cech modelu HD.",
    ]
    if request.log_format == "hdfs":
        warnings.append("HDFS: host pozostaje null. Adres w tresci logu nie musi oznaczac hosta zrodla.")
        if any(not event.block_ids for event in events):
            warnings.append("Wpisy bez BlockID pozostaja w events, ale nie tworza sekwencji HDFS.")
    else:
        warnings.append("Grupowanie SSH po hoscie jest demonstracyjne; okna czasu wymagaja uzgodnienia.")
    return AnalysisResponse(
        analysis_id=analysis_id, events=events,
        groups=group_events(events, request.log_format), warnings=warnings,
    )
