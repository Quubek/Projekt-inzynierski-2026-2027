"""Nazwy z podpowiedzią po najechaniu i pełnym opisem po kliknięciu."""

import streamlit as st

from log_analyzer.contracts import Finding, RuleDefinition
from log_analyzer.detection.catalog import finding_rules
from log_analyzer.dashboard.navigation import navigate


def render_rule(rule: RuleDefinition) -> None:
    with st.popover(f"**{rule.name}**", icon=":material/info:", help=rule.description, width="stretch"):
        st.text(rule.description)
        st.caption(f"{rule.rule_id} · {rule.version}")


def render_finding_rules(finding: Finding) -> None:
    rules = finding_rules(finding)
    if not rules:
        return
    st.caption("Dopasowane reguły — najedź na nazwę lub kliknij, aby przeczytać opis.")
    for rule in rules:
        render_rule(rule)


def render_rule_legend() -> None:
    with st.container(border=True):
        st.subheader("Jak działają reguły?")
        st.write("Reguły sprawdzają określone wzorce zdarzeń i ich powtarzalność. "
                 "Dopasowanie wskazuje zachowanie wymagające sprawdzenia — nie potwierdza ataku ani awarii.")
        st.caption("Katalog opisuje warunki aktualnych reguł HDFS. Progi są demonstracyjne. "
                   "W szczegółach wykrycia i raportu znajdziesz opis reguły użytej podczas analizy.")
        st.button("Przeglądaj reguły", key="open_rule_catalog", width="stretch",
                  on_click=navigate, args=("rules",))
