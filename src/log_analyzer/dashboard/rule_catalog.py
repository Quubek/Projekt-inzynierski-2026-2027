"""Przeszukiwalny katalog aktualnych definicji, wspólnych z detektorem."""

import math

import streamlit as st

from log_analyzer.detection.catalog import RULE_NAMES, RULES_VERSION, rule_definition


PAGE_SIZE = 25


def render_rule_catalog() -> None:
    st.title("Katalog reguł")
    st.write("Warunki wskazywania zachowań do sprawdzenia. Dopasowanie reguły nie potwierdza incydentu.")
    st.caption(f"Aktualna wersja: {RULES_VERSION}. Historyczne raporty zachowują opis użytej reguły.")
    query = st.text_input("Szukaj po ID, nazwie lub opisie", key="rule_catalog_search").strip().casefold()
    rules = [rule_definition(rule_id) for rule_id in RULE_NAMES]
    rules = [rule for rule in rules if not query or query in
             f"{rule.rule_id} {rule.name} {rule.description}".casefold()]
    if st.session_state.get("rule_catalog_query") != query:
        st.session_state["rule_catalog_page"] = 1
        st.session_state["rule_catalog_query"] = query
    pages = max(1, math.ceil(len(rules) / PAGE_SIZE))
    if st.session_state.get("rule_catalog_page", 1) > pages:
        st.session_state["rule_catalog_page"] = 1
    page = st.number_input("Strona katalogu", min_value=1, max_value=pages,
                           step=1, key="rule_catalog_page")
    st.caption(f"Znalezione reguły: {len(rules)} · Strona {page} z {pages}")
    if not rules:
        st.info("Brak reguł pasujących do wyszukiwania.")
        return
    for index, rule in enumerate(rules[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]):
        if index == 0:
            identifier, name, description = st.columns([1, 2, 5])
            identifier.markdown("**ID reguły**")
            name.markdown("**Nazwa reguły**")
            description.markdown("**Opis reguły**")
        with st.container(border=True):
            identifier, name, description = st.columns([1, 2, 5])
            identifier.text(rule.rule_id)
            name.markdown(f"**{rule.name}**")
            description.text(rule.description)
