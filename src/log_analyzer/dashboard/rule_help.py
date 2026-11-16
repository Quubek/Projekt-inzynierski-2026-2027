"""Nazwy z podpowiedzią po najechaniu i pełnym opisem po kliknięciu."""

import streamlit as st

from log_analyzer.contracts import Finding, RuleDefinition
from log_analyzer.detection.catalog import RULE_NAMES, finding_rules, rule_definition


def render_rule(rule: RuleDefinition) -> None:
    with st.popover(rule.name, icon=":material/info:", help=rule.description, width="stretch"):
        st.text(rule.description)
        st.caption(f"{rule.rule_id} · {rule.version}")


def render_finding_rules(finding: Finding) -> None:
    st.caption("Dopasowane reguły — najedź na nazwę lub kliknij, aby przeczytać opis.")
    for rule in finding_rules(finding):
        render_rule(rule)


def render_rule_legend() -> None:
    with st.container(border=True):
        st.subheader("Jak działają reguły?")
        st.caption("Spis reguł HDFS. Najedź na nazwę lub kliknij ⓘ, aby zobaczyć warunki.")
        for rule_id in RULE_NAMES:
            rule = rule_definition(rule_id)
            render_rule(rule)
            st.caption(rule.description.split(". ", 1)[0] + ".")
        st.caption("Reguły wskazują zachowania do sprawdzenia. Progi są demonstracyjne i nie stanowią potwierdzenia incydentu.")
