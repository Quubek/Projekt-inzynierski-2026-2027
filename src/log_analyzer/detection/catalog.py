"""Wspólne nazwy i opisy reguł; zapis wykrycia zachowuje użyte opisy."""

from log_analyzer.contracts import Finding, RuleDefinition

RULES_VERSION = "hdfs-rules-v1"
EXCEPTION_BURST_COUNT = 3
EXCEPTION_WINDOW_SECONDS = 300
LARGE_DELETE_BLOCKS = 50

RULE_NAMES = {
    "HDFS-001": "Problem z udostępnianiem bloku",
    "HDFS-002": "Powtarzające się problemy węzła",
    "HDFS-003": "Żądanie usunięcia wielu bloków",
}


def rule_definition(rule_id: str, *, version: str = RULES_VERSION, details: dict | None = None) -> RuleDefinition:
    details = details or {}
    name = RULE_NAMES.get(rule_id, rule_id)
    if version != RULES_VERSION or rule_id not in RULE_NAMES:
        description = "Opis tej wersji reguły nie został zapisany. Warunki konkretnego wskazania sprawdź w jego uzasadnieniu."
    elif rule_id == "HDFS-001":
        description = (
            "Wskazuje komunikaty o wyjątkach podczas udostępniania bloków i łączy je według węzła. "
            "Sam wyjątek nie potwierdza awarii ani ataku."
        )
    elif rule_id == "HDFS-002":
        count = details.get("threshold", EXCEPTION_BURST_COUNT)
        seconds = int(details.get("window_seconds", EXCEPTION_WINDOW_SECONDS))
        window = f"{seconds // 60} min" if seconds % 60 == 0 else f"{seconds} s"
        description = (
            f"Wskazuje co najmniej {count} wyjątki udostępniania bloków dla jednego węzła w ciągu {window}. "
            "Próg jest demonstracyjny, a wskazanie wymaga sprawdzenia."
        )
    else:
        count = details.get("threshold", LARGE_DELETE_BLOCKS)
        description = (
            f"Wskazuje pojedyncze żądanie usunięcia co najmniej {count} różnych bloków. "
            "Może to być prawidłowa operacja utrzymaniowa; żądanie nie oznacza potwierdzenia usunięcia."
        )
    return RuleDefinition(rule_id=rule_id, version=version, name=name, description=description)


def finding_rules(finding: Finding) -> list[RuleDefinition]:
    saved = {rule.rule_id: rule for rule in finding.rule_definitions}
    return [saved.get(rule_id) or rule_definition(rule_id, version=finding.rules_version, details=finding.details)
            for rule_id in finding.rule_ids]


def finding_title(finding: Finding) -> str:
    if finding.source == "rules" and finding.rule_ids:
        definitions = {rule.rule_id: rule for rule in finding_rules(finding)}
        primary = "HDFS-002" if "HDFS-002" in definitions else finding.rule_ids[0]
        return definitions[primary].name
    return finding.title
