"""Wspólna nawigacja, także dla raportów otwieranych z przyszłej analizy."""

import streamlit as st


VIEWS = {
    "home": "Start",
    "analysis": "Analiza logów",
    "findings": "Wykrycia i anomalie",
    "history": "Historia raportów",
    "evaluation": "Ocena modeli",
    "rules": "Katalog reguł",
}


def navigate(
    view: str, report_id: str | None = None, back: str = "history", *,
    finding_id: str | None = None, analysis_id: str | None = None,
) -> None:
    params = {"view": view}
    if view == "report" and report_id:
        params.update(report_id=report_id, back=back)
        if finding_id:
            params["finding_id"] = finding_id
    if view == "finding" and finding_id:
        params["finding_id"] = finding_id
    if view == "findings" and analysis_id:
        params["analysis_id"] = analysis_id
    st.query_params.from_dict(params)


def render_navigation(view: str) -> None:
    if view == "home":
        return

    if view in ("report", "finding"):
        home, previous, _ = st.columns([1, 1, 3])
    else:
        home = st.container()

    home.button(
        "← Powrót do startu", key="back_to_home",
        on_click=navigate, args=("home",),
    )
    if view == "report":
        back = st.query_params.get("back", "history")
        if back not in ("history", "analysis", "finding"):
            back = "history"
        previous.button(
            {"history": "← Wróć do historii", "analysis": "← Wróć do analizy", "finding": "← Wróć do wykrycia"}[back],
            key="back_from_report", on_click=navigate, args=(back,),
            kwargs={"finding_id": st.query_params.get("finding_id")} if back == "finding" else None,
        )
    elif view == "finding":
        previous.button("← Wróć do wykryć", key="back_to_findings", on_click=navigate, args=("findings",))
