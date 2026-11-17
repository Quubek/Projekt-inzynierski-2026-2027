"""Wejście do istniejącego parsera API. Detekcja pozostaje osobnym etapem."""

import os
import hashlib
from collections import Counter
from datetime import datetime

import streamlit as st
from pydantic import ValidationError

from log_analyzer.contracts import MAX_LOG_LINES, AnalysisResponse, AnalyzeRequest
from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApiError
from log_analyzer.dashboard.navigation import navigate
from log_analyzer.dashboard.presentation import EVENT_TYPES, event_time


MAX_INPUT_BYTES = 2 * 1024 * 1024


def decode_log_file(content: bytes) -> str:
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError("Plik może mieć maksymalnie 2 MB.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Nie można odczytać pliku. Zapisz go w kodowaniu UTF-8.") from error


def prepare_request(text: str, log_format: str, **options) -> AnalyzeRequest:
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Przekazany tekst może mieć maksymalnie 2 MB.")
    lines = [line for line in text.lstrip("\ufeff").splitlines() if line.strip()]
    if not lines:
        raise ValueError("Wklej logi lub wybierz plik zawierający zdarzenia.")
    if len(lines) > MAX_LOG_LINES:
        raise ValueError(f"Jedna paczka może zawierać maksymalnie {MAX_LOG_LINES} niepustych wpisów.")
    if any(len(line.strip()) > 10000 for line in lines):
        raise ValueError("Pojedynczy wpis może mieć maksymalnie 10 000 znaków.")
    try:
        return AnalyzeRequest.model_validate({"logs": lines, "log_format": log_format, **options})
    except ValidationError as error:
        raise ValueError("Sprawdź format logów (SSH/HDFS), strefę czasową i rok źródła.") from error


def render_analysis_result(result: AnalysisResponse) -> None:
    st.divider()
    st.subheader("Wynik przetwarzania")
    levels = Counter(event.log_level for event in result.events)
    st.caption(
        f"Zdarzenia: {len(result.events)} · WARN: {levels['WARN']} · Komponenty: "
        f"{len({event.component for event in result.events})} · Grupy: {len(result.groups)} · Wykrycia: {len(result.findings)}"
    )
    detection_text = {
        "not_configured": "Model ML: niepodłączony.",
        "completed": "Model ML ocenił grupy HDFS.",
        "partial": "Model ML ocenił tylko część grup; niektóre cechy były nieznane.",
    }[result.detection_status]
    st.info(
        "Przetwarzanie zakończono. " + detection_text + " "
        + ("Reguły HDFS zostały sprawdzone. " if result.rules_status == "completed" else "Reguły HDFS nie dotyczą tego formatu. ")
        + "Wynik nie rozstrzyga, czy doszło do awarii lub ataku."
    )
    st.caption(f"ID analizy: {result.analysis_id} · Strefa źródła: {result.source_timezone or 'nie określono'}")
    if result.findings:
        st.button("Przejdź do wykryć tej analizy", key="analysis_findings", on_click=navigate,
                  args=("findings",), kwargs={"analysis_id": result.analysis_id})
    events, groups = st.tabs(["Zdarzenia", "Grupy zdarzeń"])
    with events:
        filtered = filter_events(result)
        st.caption(f"Wyświetlane wpisy: {len(filtered)} z {len(result.events)}. Wybierz wiersz, aby zobaczyć źródło i parametry.")
        table = st.dataframe([{
            "Nr wpisu": event.source_line,
            "Czas": event_time(event), "Poziom logu": event.log_level or "Nie podano",
            "Komponent": event.component,
            "Operacja": EVENT_TYPES.get(event.event_type, event.event_type),
            "Komunikat": event.message,
        } for event in filtered], hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key=f"analysis_events_{result.analysis_id}_{hashlib.sha256('|'.join(e.event_id for e in filtered).encode()).hexdigest()[:12]}")
        if table.selection.rows and table.selection.rows[0] < len(filtered):
            render_event_details(filtered[table.selection.rows[0]])
        st.caption("Czasy z jawną strefą przeliczono na UTC. Pozostałe pozostają czasami źródłowymi.")
    with groups:
        if result.groups:
            by_id = {event.event_id: event for event in result.events}
            st.dataframe([{
                "Grupa": group.group_id, "Liczba zdarzeń": len(group.event_ids),
                "Pierwszy dostępny czas": group_time_bounds([by_id[eid] for eid in group.event_ids])[0],
                "Ostatni dostępny czas": group_time_bounds([by_id[eid] for eid in group.event_ids])[1],
                "Ocena ML": (
                    f"{group.ml_prediction} · {group.ml_score:.3f}"
                    if group.ml_prediction and group.ml_score is not None else "Nie oceniono"
                ),
            } for group in result.groups], hide_index=True, width="stretch")
        else:
            st.caption("Dla tych wpisów nie utworzono grup zdarzeń.")
    with st.expander("Uwagi do wyniku"):
        if not result.warnings:
            st.caption("Brak dodatkowych uwag do tej analizy.")
        for warning in result.warnings:
            st.text(warning)
    with st.expander("Diagnostyka techniczna"):
        for diagnostic in result.diagnostics:
            st.text(diagnostic)
    with st.expander("Pełna odpowiedź analizy"):
        st.json(result.model_dump(mode="json"))
    if result.groups:
        render_group_reporting(result)
    st.caption("Analiza jest zapisana przez API. Historia raportów zawiera wygenerowane raporty.")


def filter_events(result):
    prefix = result.analysis_id
    with st.expander("Filtry zdarzeń"):
        level_col, component_col, search_col = st.columns([1, 2, 2])
        level = level_col.selectbox("Poziom logu", ["Wszystkie", *sorted({e.log_level for e in result.events if e.log_level})], key=f"level_{prefix}")
        component = component_col.selectbox("Komponent", ["Wszystkie", *sorted({e.component for e in result.events})], key=f"component_{prefix}")
        query = search_col.text_input("IP, BlockID lub fragment komunikatu", key=f"search_{prefix}").strip().casefold()
        start_col, end_col = st.columns(2)
        start = start_col.date_input("Data źródłowa od", value=None, key=f"event_from_{prefix}")
        end = end_col.date_input("Data źródłowa do", value=None, key=f"event_to_{prefix}")
        st.caption("Filtr dat dotyczy lokalnej daty źródłowej, jeżeli jest dostępna.")
    if start and end and start > end:
        st.warning("Data początkowa nie może być późniejsza od końcowej.")
        return []
    filtered = []
    for event in result.events:
        if level != "Wszystkie" and event.log_level != level:
            continue
        if component != "Wszystkie" and event.component != component:
            continue
        if query and query not in event.raw.casefold():
            continue
        local_date = datetime.fromisoformat(event.timestamp_local).date() if event.timestamp_local else None
        if (start or end) and local_date is None:
            continue
        if (start and local_date < start) or (end and local_date > end):
            continue
        filtered.append(event)
    return filtered


def group_time_bounds(events):
    if all(event.timestamp for event in events):
        times = [event.timestamp for event in events]
    elif all(event.timestamp_local and event.timezone_source == "unknown" for event in events):
        times = [event.timestamp_local for event in events]
    else:
        return "Nie ustalono wspólnego czasu", "Nie ustalono wspólnego czasu"
    return min(times), max(times)


def render_event_details(event):
    st.subheader(f"Szczegóły wpisu {event.source_line or event.event_id}")
    st.code(event.raw, language="text", wrap_lines=True)
    st.text(f"Host źródłowy: {event.host or 'Nie ustalono'}")
    st.text("Pochodzenie strefy: " + {"log": "z logu", "configuration": "z ustawień źródła", "unknown": "nie ustalono"}[event.timezone_source])
    st.json(event.parameters)
    if event.block_ids:
        with st.expander(f"Powiązane bloki ({len(event.block_ids)})"):
            st.code("\n".join(event.block_ids), language="text")
    with st.expander("Szablon i identyfikator zdarzenia"):
        st.code(event.template, language="text", wrap_lines=True)
        st.text(event.event_id)


def render_group_reporting(result: AnalysisResponse) -> None:
    with st.container(border=True):
        st.subheader("Raport z grupy zdarzeń")
        st.caption(
            "Ręczny wybór grupy nie oznacza wykrycia anomalii. "
            "Generowanie wymaga uruchomionej Ollamy i może potrwać do dwóch minut."
        )
        group = st.selectbox(
            "Grupa do opisania", options=[item.group_id for item in result.groups],
            key=f"report_group_{result.analysis_id}",
        )
        key = f"{result.analysis_id}:{group}"
        saved_reports = st.session_state.setdefault("analysis_reports", {})
        if st.button("Generuj raport", key="generate_group_report", disabled=key in saved_reports):
            try:
                with st.spinner("Generowanie i zapisywanie raportu…"):
                    with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
                        report = api.generate_report(result.analysis_id, group)
                saved_reports[key] = str(report.report_id)
            except ReportsApiError as error:
                st.error(str(error))
        if key in saved_reports:
            st.success("Raport został zapisany. Jest również dostępny w historii.")
            st.button(
                "Otwórz raport", key="open_analysis_report", type="primary",
                on_click=navigate, args=("report", saved_reports[key], "analysis"),
            )


def render_analysis() -> None:
    st.caption("ANALIZATOR LOGÓW / ANALIZA")
    st.title("Analiza logów")
    st.write("Prześlij logi i sprawdź ich podział na zdarzenia oraz grupy.")
    st.caption("Obecnie dostępne: przyjmowanie i parsowanie logów SSH oraz HDFS.")
    mode = st.radio(
        "Źródło logów", ["Wklej tekst", "Prześlij plik"],
        horizontal=True, key="analysis_input_mode",
    )
    for key, default in (("analysis_text", ""), ("analysis_format", "ssh")):
        if key not in st.session_state:
            st.session_state[key] = st.session_state.get("saved_" + key, default)
    with st.form("analysis_form"):
        log_format = st.selectbox(
            "Format logów", ["ssh", "hdfs"], key="analysis_format",
            format_func=lambda value: "SSH / auth.log" if value == "ssh" else "HDFS",
        )
        with st.expander("Informacje o źródle"):
            zone = st.text_input("Strefa czasowa źródła — opcjonalnie", placeholder="Europe/Warsaw lub UTC", key="source_timezone").strip()
            year_text = st.text_input("Rok źródła — tylko dla wpisów SSH bez roku", placeholder="np. 2026", max_chars=4, key="source_year").strip()
            scope = st.selectbox("Kompletność danych", ["unknown", "sample", "complete"],
                                 format_func=lambda value: {"unknown": "Nie ustalono", "sample": "Próbka danych", "complete": "Deklaruję pełny zapis"}[value], key="source_scope")
            st.caption("Nie wpisuj strefy laptopa, jeśli nie znasz strefy zapisanej w źródle. Strefa jawna w logu ma pierwszeństwo.")
        text = ""
        upload = None
        if mode == "Wklej tekst":
            text = st.text_area(
                "Logi — jeden wpis w wierszu", height=220, key="analysis_text",
                max_chars=MAX_INPUT_BYTES,
                placeholder="Nov 4 10:14:03 server01 sshd[1234]: Failed password for admin from 192.0.2.10 port 51234 ssh2",
            )
        else:
            upload = st.file_uploader(
                "Wybierz plik .log lub .txt", type=["log", "txt"], key="analysis_file",
                help=f"Kodowanie UTF-8, maksymalnie 2 MB i {MAX_LOG_LINES} niepustych wpisów.",
            )
        st.caption(f"Puste wiersze są pomijane. Maksymalnie {MAX_LOG_LINES} wpisów w jednej paczce.")
        submitted = st.form_submit_button("Sprawdź logi", key="submit_analysis", type="primary")

    st.session_state["saved_analysis_format"] = log_format
    if mode == "Wklej tekst":
        st.session_state["saved_analysis_text"] = text
    if submitted:
        # Błąd nowej próby nie może pozostawić na ekranie wyniku wcześniejszej paczki.
        st.session_state.pop("analysis_result", None)
        try:
            if mode == "Prześlij plik":
                if upload is None:
                    raise ValueError("Wybierz plik z logami.")
                text = decode_log_file(upload.getvalue())
            if year_text and not year_text.isdecimal():
                raise ValueError("Rok źródła musi być liczbą, np. 2026.")
            request = prepare_request(text, log_format, source_timezone=zone or None,
                                      source_year=int(year_text) if year_text else None, data_scope=scope)
            with st.spinner("Przetwarzanie logów…"):
                with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
                    result = api.analyze(request)
            st.session_state["analysis_result"] = result.model_dump(mode="json")
        except (ValueError, ReportsApiError) as error:
            st.error(str(error))

    if "analysis_result" in st.session_state:
        try:
            result = AnalysisResponse.model_validate(st.session_state["analysis_result"])
        except ValidationError:
            st.session_state.pop("analysis_result", None)
            st.info("Poprzedni wynik ma inny format danych. Prześlij logi ponownie.")
        else:
            render_analysis_result(result)
