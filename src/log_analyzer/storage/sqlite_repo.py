import json
import sqlite3
from contextlib import closing
from pathlib import Path


KATALOG_PROJEKTU = Path(__file__).resolve().parents[3]
SCIEZKA_BAZY = KATALOG_PROJEKTU / "runtime" / "raporty.sqlite3"


def inicjalizuj_baze() -> None:
    SCIEZKA_BAZY.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(SCIEZKA_BAZY)) as polaczenie:
        polaczenie.execute(
            """
            CREATE TABLE IF NOT EXISTS raporty (
                report_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                host TEXT,
                raport_json TEXT NOT NULL
            )
            """
        )
        polaczenie.commit()


def zapisz_raport(raport_json: str) -> None:
    dane = json.loads(raport_json)

    with closing(sqlite3.connect(SCIEZKA_BAZY)) as polaczenie:
        polaczenie.execute(
            """
            INSERT INTO raporty (
                report_id, created_at, host, raport_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                dane["report_id"],
                dane["created_at"],
                dane["host"],
                raport_json,
            ),
        )
        polaczenie.commit()


def pobierz_raport(report_id: str) -> str | None:
    with closing(sqlite3.connect(SCIEZKA_BAZY)) as polaczenie:
        wynik = polaczenie.execute(
            "SELECT raport_json FROM raporty WHERE report_id = ?",
            (report_id,),
        ).fetchone()

    if wynik is None:
        return None

    return wynik[0]