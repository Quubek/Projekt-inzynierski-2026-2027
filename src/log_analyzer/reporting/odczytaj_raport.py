import argparse
from uuid import UUID

from log_analyzer.reporting.ollama_klient import RaportZdarzen
from log_analyzer.storage.sqlite_repo import (
    SCIEZKA_BAZY,
    pobierz_raport,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Odczytuje raport z SQLite po identyfikatorze."
    )
    parser.add_argument(
        "report_id",
        type=UUID,
        help="Identyfikator zapisanego raportu.",
    )
    argumenty = parser.parse_args()

    if not SCIEZKA_BAZY.is_file():
        raise SystemExit("Baza nie istnieje. Najpierw zapisz raport.")

    raport_json = pobierz_raport(str(argumenty.report_id))

    if raport_json is None:
        raise SystemExit("Nie znaleziono raportu o podanym ID.")

    raport = RaportZdarzen.model_validate_json(raport_json)

    print("\nRaport odczytany z SQLite:")
    print(raport.model_dump_json(indent=2))


if __name__ == "__main__":
    main()