"""Panel projektu z osobnymi widokami historii i szczegółów raportu."""

import hashlib
import json
import math
import os
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

import streamlit as st

from log_analyzer.contracts import RaportZdarzen
from log_analyzer.dashboard.api_client import ReportsApi, ReportsApiError
from log_analyzer.dashboard.analysis import render_analysis
from log_analyzer.dashboard.evaluation import render_evaluation
from log_analyzer.dashboard.findings import render_finding_page, render_findings
from log_analyzer.dashboard.rule_help import render_finding_rules, render_rule_legend
from log_analyzer.detection.catalog import finding_title
from log_analyzer.dashboard.navigation import VIEWS, navigate, render_navigation


FILTER_DEFAULTS = {
    "filter_id": "", "filter_host": ("all", ""),
    "filter_from": None, "filter_to": None,
}


def format_time(value: datetime | None) -> str:
    if value is None:
        return "Brak danych"
    if value.tzinfo is None:
        return value.strftime("%d.%m.%Y %H:%M:%S") + " (bez strefy)"
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")


def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["saved_history_filters"] = FILTER_DEFAULTS.copy()
    st.session_state["history_page"] = 1
    st.session_state["saved_history_page"] = 1


def render_filters(hosts: list[str]) -> dict:
    saved = st.session_state.get("saved_history_filters", FILTER_DEFAULTS)
    for key, default in FILTER_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = saved.get(key, default)
    with st.expander("Filtry raportów", expanded=any(saved.get(key) != value for key, value in FILTER_DEFAULTS.items())):
        st.caption("Daty dotyczą utworzenia raportu, w strefie UTC.")
        search, host_filter, start, end = st.columns([2, 2, 1, 1])
        query = search.text_input(
            "Identyfikator raportu", placeholder="Wpisz całe ID lub fragment",
            max_chars=64, key="filter_id",
        ).strip()
        choices = [("all", ""), ("unknown", ""), *[("host", host) for host in hosts]]
        if st.session_state.get("filter_host") not in choices:
            st.session_state.pop("filter_host", None)
        selected = host_filter.selectbox(
            "Host", options=choices, key="filter_host",
            format_func=lambda item: (
                "Wszystkie hosty" if item[0] == "all" else
                "Brak danych o hoście" if item[0] == "unknown" else item[1]
            ),
        )
        date_from = start.date_input("Utworzono od", value=None, key="filter_from", format="DD.MM.YYYY")
        date_to = end.date_input("Utworzono do", value=None, key="filter_to", format="DD.MM.YYYY")
        st.button("Wyczyść filtry", key="clear_filters", on_click=reset_filters)

    # Wartości niezwiązane z widgetami pozostają po zmianie widoku.
    st.session_state["saved_history_filters"] = {
        key: st.session_state[key] for key in FILTER_DEFAULTS
    }

    if date_from and date_to and date_from > date_to:
        st.warning("Data początkowa nie może być późniejsza od końcowej.")
        st.stop()
    params = {}
    if query:
        params["report_id_query"] = query
    if selected[0] == "host":
        params["host"] = selected[1]
    elif selected[0] == "unknown":
        params["unknown_host"] = True
    if date_from:
        params["created_from"] = datetime.combine(date_from, time.min, timezone.utc).isoformat()
    if date_to:
        params["created_before"] = datetime.combine(
            date_to + timedelta(days=1), time.min, timezone.utc
        ).isoformat()
    return params


def render_report(report: RaportZdarzen) -> None:
    title, download = st.columns([3, 1], vertical_alignment="center")
    title.title("Szczegóły raportu")
    download.download_button(
        "Pobierz JSON", data=report.model_dump_json(indent=2).encode("utf-8"),
        file_name=f"raport-{report.report_id}.json", mime="application/json",
        width="stretch", on_click="ignore",
    )
    st.caption(f"ID raportu: {report.report_id}")
    st.caption(
        f"Host: {report.host or 'Brak danych'} · Zdarzenia: {report.liczba_zdarzen} · "
        f"Utworzono: {format_time(report.created_at)}"
    )
    if report.finding:
        render_finding_rules(report.finding)
    if report.llm_input_mode == "aggregated":
        st.info(f"LLM otrzymał agregaty wszystkich {report.liczba_zdarzen} zdarzeń i {len(report.llm_event_ids)} przykładów. "
                f"Pozostałych {report.llm_omitted_events} wpisów nie przekazano w oryginalnej postaci. Pełne logi zachowano w źródłach raportu.")
    summary, sources, metadata = st.tabs(["Podsumowanie", "Zdarzenia źródłowe", "Dane raportu"])
    with summary:
        with st.container(border=True):
            st.subheader("Co się wydarzyło")
            st.text(report.tresc.podsumowanie)
        with st.container(border=True):
            st.subheader("Rekomendacja modelu")
            st.text(report.tresc.rekomendacja)
            st.caption("Treść wygenerowana przez LLM wymaga oceny analityka.")
    with sources:
        st.subheader("Oryginalne logi")
        st.caption("Identyfikatory i treść zdarzeń wykorzystanych w raporcie.")
        st.code("\n\n".join(report.tresc.kluczowe_zdarzenia), language="text", wrap_lines=True)
    with metadata:
        st.subheader("Metadane")
        st.text(f"Identyfikator: {report.report_id}")
        st.text(f"Host: {report.host or 'Brak danych'}")
        st.text(f"Utworzono raport: {format_time(report.created_at)}")
        st.text(f"Liczba zdarzeń: {report.liczba_zdarzen}")
        if report.analysis_id:
            st.text(f"Analiza źródłowa: {report.analysis_id}")
            if report.group_id:
                st.text(f"Grupa: {report.group_id}")
            st.caption("Raport uruchomiono ręcznie. Samo wygenerowanie raportu nie potwierdza anomalii.")
        if report.finding:
            st.text(f"Wykrycie: {finding_title(report.finding)}")
        st.markdown("#### Czas zdarzeń")
        if report.czas_od is not None:
            st.write(f"{format_time(report.czas_od)} → {format_time(report.czas_do)}")
        elif report.czas_zrodlowy_od:
            st.write(f"{report.czas_zrodlowy_od} → {report.czas_zrodlowy_do}")
            st.caption("Przedział czasu źródłowego. Nie przeliczono go na UTC.")
        else:
            st.caption("Brak danych pozwalających ustalić przedział czasu zdarzeń.")
        if report.liczba_zdarzen_bez_czasu:
            st.warning(
                f"Zdarzenia bez czasu ze strefą umożliwiającą przeliczenie na UTC: {report.liczba_zdarzen_bez_czasu} "
                f"z {report.liczba_zdarzen}. Czas utworzenia raportu nie jest czasem zdarzeń."
            )
        with st.expander("Pełny raport JSON"):
            st.json(report.model_dump(mode="json"))


def render_home() -> None:
    st.caption("ANALIZATOR LOGÓW / START")
    st.title("Co chcesz zrobić?")
    st.write("Wybierz obszar pracy. Każda część ma swój osobny widok.")
    st.write("")
    cards = [
        ("analysis", "01", "Analiza logów",
         "Przesyłanie logów, filtry zdarzeń, grupy i reguły HDFS.", "Dostępne"),
        ("findings", "02", "Wykrycia i anomalie",
         "Sygnały do sprawdzenia, uzasadnienia reguł i zdarzenia źródłowe.", "Reguły HDFS"),
        ("history", "03", "Historia raportów",
         "Wyszukiwanie zapisanych raportów, szczegóły i pobieranie JSON.", "Dostępne"),
        ("evaluation", "04", "Ocena modeli",
         "Metryki eksperymentów i porównanie metod wykrywania anomalii.", "Odczyt wyników"),
    ]
    tiles, legend = st.columns([2, 1], gap="large")
    with tiles:
        for start in range(0, len(cards), 2):
            for column, (view, number, title, description, status) in zip(st.columns(2), cards[start:start + 2]):
                with column, st.container(border=True):
                    st.caption(f"{number} / {status}")
                    st.subheader(title)
                    st.write(description)
                    st.button("Otwórz", key=f"tile_{view}", width="stretch",
                              type="primary" if view == "history" else "secondary", on_click=navigate, args=(view,))
    with legend:
        render_rule_legend()


def render_history() -> None:
    st.caption("ANALIZATOR LOGÓW / HISTORIA")
    title, refresh = st.columns([4, 1], vertical_alignment="bottom")
    title.title("Historia raportów")
    title.caption("Znajdź raport i otwórz go w osobnym widoku.")
    refresh.button("Odśwież", key="refresh_history", width="stretch")

    api_url = os.getenv("API_URL", "http://127.0.0.1:8000")
    try:
        with ReportsApi(api_url) as api:
            overview = api.history(limit=25)
            params = render_filters(overview.known_hosts)
            history = api.history(limit=25, **params) if params else overview

            fingerprint = json.dumps(params, sort_keys=True)
            if st.session_state.get("history_filters") != fingerprint:
                st.session_state["history_page"] = 1
                st.session_state["saved_history_page"] = 1
                st.session_state["history_filters"] = fingerprint
            if not history.total:
                if overview.total:
                    st.info("Brak raportów pasujących do filtrów. Zmień lub wyczyść filtry.")
                else:
                    st.info("Historia jest pusta. Raporty pojawią się po zapisaniu wyników analizy.")
                return

            pages = math.ceil(history.total / 25)
            if "history_page" not in st.session_state:
                st.session_state["history_page"] = st.session_state.get("saved_history_page", 1)
            if st.session_state.get("history_page", 1) > pages:
                st.session_state["history_page"] = 1
            table_title, pagination = st.columns([3, 1], vertical_alignment="bottom")
            table_title.caption(
                f"Znaleziono raportów: {history.total} · Znane hosty: {history.known_host_count}"
            )
            page = pagination.number_input(
                "Strona", min_value=1, max_value=pages, step=1, key="history_page",
            )
            st.session_state["saved_history_page"] = page
            offset = (page - 1) * 25
            if offset:
                history = api.history(limit=25, offset=offset, **params)
            if not history.reports:
                st.info("Lista raportów zmieniła się. Odśwież historię.")
                return

            st.caption(
                f"Wyświetlono {offset + 1}–{offset + len(history.reports)} "
                f"z {history.total}. Zaznacz wiersz i kliknij „Otwórz raport”."
            )
            rows = [{
                "Utworzono (UTC)": format_time(item.created_at),
                "Host": item.host or "Brak danych",
                "Zdarzenia": item.liczba_zdarzen,
                "Podsumowanie": item.podsumowanie or "Brak podsumowania",
                "ID": str(item.report_id)[:8],
            } for item in history.reports]
            ids = ":".join(str(item.report_id) for item in history.reports)
            table_key = hashlib.sha256(f"{fingerprint}:{page}:{ids}".encode()).hexdigest()[:16]
            table = st.dataframe(
                rows, hide_index=True, width="stretch", on_select="rerun",
                selection_mode="single-row", key=f"reports_{table_key}",
                column_config={
                    "Zdarzenia": st.column_config.NumberColumn(format="%d", width="small"),
                    "Podsumowanie": st.column_config.TextColumn(width="large"),
                    "ID": st.column_config.TextColumn(width="small"),
                },
            )
            selected_rows = table.selection.rows
            index = selected_rows[0] if selected_rows else None
            selected_id = (
                str(history.reports[index].report_id)
                if index is not None and index < len(history.reports) else None
            )
            st.button(
                "Otwórz raport", key="open_report", type="primary",
                disabled=selected_id is None, on_click=navigate,
                args=("report", selected_id, "history"),
            )
    except ReportsApiError as error:
        st.error(str(error))
        st.caption("Użyj przycisku „Odśwież” po przywróceniu połączenia z API.")


def render_report_page() -> None:
    try:
        report_id = str(UUID(st.query_params.get("report_id", "")))
    except ValueError:
        st.error("Niepoprawny identyfikator raportu.")
        return
    try:
        with ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
            render_report(api.report(report_id))
    except ReportsApiError as error:
        st.error(str(error))
        st.button("Spróbuj ponownie", key="retry_report")


def main() -> None:
    st.set_page_config(
        page_title="Analizator logów", page_icon="🔎",
        layout="wide", initial_sidebar_state="collapsed",
    )
    st.markdown(
        """<style>
        .block-container { max-width: 1300px; padding-top: 5.5rem; padding-bottom: 3rem; }
        section[data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stText"] { line-height: 1.65; }
        </style>""", unsafe_allow_html=True,
    )
    view = st.query_params.get("view", "home")
    if view not in (*VIEWS, "report", "finding"):
        view = "home"
    render_navigation(view)
    if view == "home":
        render_home()
    elif view == "history":
        render_history()
    elif view == "report":
        render_report_page()
    elif view == "analysis":
        render_analysis()
    elif view == "findings":
        render_findings()
    elif view == "finding":
        render_finding_page()
    else:
        render_evaluation()


if __name__ == "__main__":
    main()
