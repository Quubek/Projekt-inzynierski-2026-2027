"""Etykiety pól wynikające z kontraktów, bez ocen generowanych przez UI."""

EVENT_TYPES = {
    "other": "Inne", "login_failed": "Nieudane logowanie", "login_succeeded": "Udane logowanie",
    "block_serving_exception": "Wyjątek udostępniania", "block_served": "Udostępnienie bloku",
    "block_receiving": "Odbieranie bloku", "block_received": "Odebranie bloku",
    "block_deleted": "Usunięcie bloku", "block_verified": "Poprawna weryfikacja",
    "block_registered": "Rejestracja bloku", "block_allocated": "Przydzielenie bloku",
    "block_deletion_scheduled": "Zaplanowane usunięcie", "block_transfer": "Transfer bloku",
    "block_delete_request": "Żądanie usunięcia", "block_replicate_request": "Żądanie replikacji",
    "responder_finished": "Zakończenie obsługi bloku",
}
PRIORITIES = {
    "unassessed": "⚪ Nie oceniono", "low": "🔵 Niski", "medium": "🟡 Średni",
    "high": "🟠 Wysoki", "critical": "🔴 Krytyczny",
}


def event_time(event):
    return event.timestamp or event.timestamp_local or event.timestamp_raw or "Brak danych"


def report_host(report):
    if report.host:
        return report.host
    if report.hosts:
        label = f"Wiele hostów ({len(report.hosts)})" if len(report.hosts) > 1 else report.hosts[0]
        if report.liczba_zdarzen_bez_hosta:
            label += " + wpisy bez hosta"
        return label
    return "Brak danych"
