"""Lista sygnałów do sprawdzenia. Bez statusów ręcznego zamykania spraw."""

import json
import math
import os
from uuid import UUID

import streamlit as st

from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApiError
from log_analyzer.dashboard.navigation import navigate
from log_analyzer.dashboard.presentation import EVENT_TYPES, PRIORITIES, event_time
from log_analyzer.dashboard.rule_help import render_finding_rules
from log_analyzer.detection.catalog import RULE_NAMES, finding_rules, finding_title


def render_findings() -> None:
    st.caption("ANALIZATOR LOGÓW / WYKRYCIA")
    st.title("Wykrycia i anomalie")
    st.caption("Sygnały wymagające sprawdzenia. Dopasowanie reguły nie potwierdza awarii ani ataku.")
    st.button("Odśwież", key="refresh_findings")
    analysis_id = st.query_params.get("analysis_id")
    if analysis_id:
        try:
            analysis_id = str(UUID(analysis_id))
        except ValueError:
            st.error("Niepoprawny identyfikator analizy.")
            return
        st.caption(f"Wykrycia analizy: {analysis_id}")
        st.button("Pokaż wszystkie analizy", on_click=navigate, args=("findings",))
    with st.expander("Filtry wykryć"):
        priority_col, rule_col, search_col = st.columns([1, 1, 2])
        saved = st.session_state.get("saved_finding_filters", {})
        for key, default in (("finding_priority", "all"), ("finding_rule", "all"), ("finding_query", "")):
            if key not in st.session_state:
                st.session_state[key] = saved.get(key, default)
        priority = priority_col.selectbox("Priorytet", ["all", *PRIORITIES], key="finding_priority",
                                           format_func=lambda value: "Wszystkie" if value == "all" else PRIORITIES[value])
        rule = rule_col.selectbox("Reguła", ["all", *RULE_NAMES], key="finding_rule",
                                  format_func=lambda value: "Wszystkie" if value == "all" else f"{RULE_NAMES[value]} ({value})")
        query = search_col.text_input("Nazwa lub adres węzła", key="finding_query", max_chars=150).strip()
        st.session_state["saved_finding_filters"] = {key: st.session_state[key] for key in ("finding_priority", "finding_rule", "finding_query")}
    params = {}
    if priority != "all":
        params["priority"] = priority
    if rule != "all":
        params["rule_id"] = rule
    if query:
        params["query"] = query
    if analysis_id:
        params["analysis_id"] = analysis_id
    fingerprint = json.dumps(params, sort_keys=True)
    if st.session_state.get("finding_filter_fingerprint") != fingerprint:
        st.session_state["finding_page"] = 1
        st.session_state["finding_filter_fingerprint"] = fingerprint
    try:
        with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
            overview = api.findings(limit=25, **params)
            if not overview.total:
                st.info("Brak wykryć pasujących do wyboru. Nie oznacza to potwierdzenia prawidłowego działania systemu.")
                return
            pages = math.ceil(overview.total / 25)
            if st.session_state.get("finding_page", 1) > pages:
                st.session_state["finding_page"] = 1
            page = st.number_input("Strona", min_value=1, max_value=pages, step=1, key="finding_page")
            history = api.findings(limit=25, offset=(page - 1) * 25, **params) if page > 1 else overview
        st.caption(f"Znaleziono: {history.total}. Priorytety reguł są wstępne; predykcje ML są oznaczone źródłem Model ML.")
        table = st.dataframe([{
            "Priorytet": PRIORITIES[item.priority], "Wskazanie": finding_title(item),
            "Węzeł": item.node or "Nie ustalono", "Zdarzenia": len(item.event_ids),
            "Reguły": ", ".join(rule.name for rule in finding_rules(item)), "Źródło": {"rules": "Reguły", "ml": "Model ML", "both": "Reguły + model"}[item.source],
            "Ocena ML": f"{item.score * 100:.1f}/100" if item.score is not None else "Nie oceniono",
        } for item in history.findings], hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key=f"findings_table_{page}_{fingerprint}")
        rows = table.selection.rows
        selected = history.findings[rows[0]].finding_id if rows and rows[0] < len(history.findings) else None
        st.button("Otwórz wykrycie", key="open_finding", disabled=selected is None, type="primary",
                  on_click=navigate, args=("finding",), kwargs={"finding_id": selected})
    except ReportsApiError as error:
        st.error(str(error))


def render_finding_page() -> None:
    st.title("Szczegóły wykrycia")
    try:
        finding_id = str(UUID(st.query_params.get("finding_id", "")))
    except ValueError:
        st.error("Niepoprawny identyfikator wykrycia.")
        return
    try:
        with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
            finding = api.finding(finding_id)
            analysis = api.analysis(finding.analysis_id)
        st.subheader(finding_title(finding))
        st.write(f"Priorytet: {PRIORITIES[finding.priority]}")
        st.text(finding.reason)
        if finding.priority_is_provisional:
            st.warning("Priorytet jest wstępny. Reguły i progi wymagają walidacji; wskazanie nie potwierdza incydentu.")
        render_finding_rules(finding)
        if finding.source == "ml":
            st.caption(f"Wersja modelu: {finding.model_version or 'nieznana'} · Grupa: {finding.node or 'BlockID'}")
        else:
            st.caption(f"Wersja reguł: {finding.rules_version} · Węzeł: {finding.node or 'Nie ustalono'}")
        st.caption(f"Ocena modelu: {finding.score * 100:.1f}/100" if finding.score is not None else "Ocena modelu ML: niedostępna")
        if finding.time_from:
            st.text(f"Czas: {finding.time_from} → {finding.time_to}")
            st.caption("Czas źródłowy bez określonej strefy." if finding.time_basis == "source_local" else "Czas przeliczony na UTC.")
        labels = {"observed_count": "Liczba zdarzeń", "threshold": "Próg reguły",
                  "window_seconds": "Okno czasu (sekundy)", "block_count": "Liczba bloków"}
        for key, value in finding.details.items():
            st.text(f"{labels.get(key, key)}: {value}")
        by_id = {event.event_id: event for event in analysis.events}
        events = [by_id[eid] for eid in finding.event_ids if eid in by_id]
        st.subheader(f"Zdarzenia źródłowe ({len(events)})")
        st.dataframe([{"Nr wpisu": event.source_line, "Czas": event_time(event),
                       "Poziom": event.log_level, "Operacja": EVENT_TYPES.get(event.event_type, event.event_type),
                       "Komunikat": event.message} for event in events], hide_index=True, width="stretch")
        with st.expander("Oryginalne logi"):
            st.code("\n\n".join(event.raw for event in events[:100]), language="text", wrap_lines=True)
            if len(events) > 100:
                st.caption(f"Podgląd pierwszych 100 z {len(events)} wpisów. Pełne źródła są dostępne do pobrania.")
        st.download_button("Pobierz źródła JSON", data=json.dumps([e.model_dump(mode="json") for e in events], ensure_ascii=False, indent=2),
                           file_name=f"zrodla-{finding_id}.json", mime="application/json", on_click="ignore")
        reports = st.session_state.setdefault("finding_reports", {})
        if st.button("Generuj raport wykrycia", key="generate_finding_report", disabled=finding_id in reports):
            with st.spinner("Generowanie raportu…"):
                with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
                    report = api.generate_report(finding.analysis_id, finding_id=finding_id)
                reports[finding_id] = str(report.report_id)
        if finding_id in reports:
            st.success("Raport zapisano w historii.")
            st.button("Otwórz raport", key="open_finding_report", on_click=navigate,
                      args=("report", reports[finding_id], "finding"), kwargs={"finding_id": finding_id})
    except ReportsApiError as error:
        st.error(str(error))
