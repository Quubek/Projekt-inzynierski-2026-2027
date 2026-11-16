"""Prezentacja zapisanych wyników detekcji z oznaczeniem pochodzenia danych."""

import os

import streamlit as st

from log_analyzer.dashboard import api_client
from log_analyzer.dashboard.api_client import ReportsApiError


def render_evaluation() -> None:
    st.caption("ANALIZATOR LOGÓW / OCENA MODELI")
    st.title("Ocena modeli")
    st.button("Odśwież", key="refresh_evaluation")
    try:
        with api_client.ReportsApi(os.getenv("API_URL", "http://127.0.0.1:8000")) as api:
            results = api.evaluation()
    except ReportsApiError as error:
        st.error(str(error))
        return
    if not results.experiments:
        st.info("Brak zapisanych wyników eksperymentów.")
        st.caption("Wyniki pojawią się po udostępnieniu pliku z metrykami przez HD.")
        return
    selected = st.selectbox(
        "Eksperyment", range(len(results.experiments)),
        format_func=lambda index: (
            f"{results.experiments[index].model} · {results.experiments[index].dataset} "
            f"· {results.experiments[index].date}"
        ),
    )
    result = results.experiments[selected]
    st.caption(
        f"Trening: {result.split.train} · Walidacja: {result.split.val} · Test: {result.split.test}"
    )
    if result.data_source == "synthetic":
        st.warning(
            "Wyniki pochodzą z danych syntetycznych. Służą do sprawdzenia prototypu "
            "i nie potwierdzają skuteczności na rzeczywistych logach."
        )
    elif result.data_source == "unknown":
        st.warning("Nie określono pochodzenia danych w pliku wyników.")
    else:
        st.caption(f"Źródło danych: Loghub · Zbiór: {result.dataset}")
    part = st.selectbox(
        "Oceniana część danych", ["validation", "test"] if result.test else ["validation"],
        format_func=lambda value: "Walidacja" if value == "validation" else "Test końcowy",
    )
    metrics = result.validation if part == "validation" else result.test
    for column, label, value in zip(
        st.columns(3), ["Precision", "Recall", "F1"],
        [metrics.precision, metrics.recall, metrics.f1],
    ):
        column.metric(label, f"{value:.4f}")
    st.caption(f"Metryki dotyczą klasy anomalii (1). Liczba ocenionych przykładów: {metrics.n}.")
    st.subheader("Macierz pomyłek")
    matrix = metrics.confusion_matrix
    st.dataframe([
        {"Rzeczywista klasa": label, "Przewidziane: normalne (0)": row[0],
         "Przewidziane: anomalia (1)": row[1]}
        for label, row in zip(["Normalne (0)", "Anomalia (1)"], matrix)
    ], hide_index=True, width="stretch")
    st.caption("Widok odczytuje zapisane wyniki. Nie uruchamia treningu ani oceny zbioru testowego.")
