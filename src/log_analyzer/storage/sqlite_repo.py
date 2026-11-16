import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
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
        polaczenie.execute(
            """
            CREATE TABLE IF NOT EXISTS analizy (
                analysis_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                analiza_json TEXT NOT NULL
            )
            """
        )
        polaczenie.execute(
            """CREATE TABLE IF NOT EXISTS wykrycia (
                finding_id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, created_at TEXT NOT NULL,
                priority TEXT NOT NULL, rule_ids TEXT NOT NULL, node TEXT, title TEXT NOT NULL,
                finding_json TEXT NOT NULL
            )"""
        )
        polaczenie.execute("CREATE INDEX IF NOT EXISTS wykrycia_analysis ON wykrycia(analysis_id)")
        polaczenie.commit()


def zapisz_analize(analiza_json: str) -> None:
    dane = json.loads(analiza_json)
    inicjalizuj_baze()
    with closing(sqlite3.connect(SCIEZKA_BAZY)) as polaczenie:
        polaczenie.execute(
            "INSERT INTO analizy (analysis_id, created_at, analiza_json) VALUES (?, ?, ?)",
            (dane["analysis_id"], datetime.now(timezone.utc).isoformat(), analiza_json),
        )
        created_at = datetime.now(timezone.utc).isoformat()
        polaczenie.executemany(
            "INSERT INTO wykrycia (finding_id, analysis_id, created_at, priority, rule_ids, node, title, finding_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(item["finding_id"], dane["analysis_id"], created_at, item["priority"],
              "|" + "|".join(item["rule_ids"]) + "|", item.get("node"), item["title"],
              json.dumps(item, ensure_ascii=False)) for item in dane.get("findings", [])],
        )
        polaczenie.commit()


def pobierz_analize(analysis_id: str) -> str | None:
    if not SCIEZKA_BAZY.is_file():
        return None
    with closing(sqlite3.connect(SCIEZKA_BAZY.resolve().as_uri() + "?mode=ro", uri=True)) as polaczenie:
        # Starsza baza może zawierać wyłącznie raporty.
        if not polaczenie.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'analizy'"
        ).fetchone():
            return None
        wynik = polaczenie.execute(
            "SELECT analiza_json FROM analizy WHERE analysis_id = ?", (analysis_id,),
        ).fetchone()
    return wynik[0] if wynik else None


def pobierz_wykrycia(*, limit=25, offset=0, analysis_id=None, priority=None, rule_id=None, query=None) -> dict:
    result = {"findings": [], "total": 0, "limit": limit, "offset": offset}
    if not SCIEZKA_BAZY.is_file():
        return result
    conditions, params = [], []
    for field, value in (("analysis_id", analysis_id), ("priority", priority)):
        if value is not None:
            conditions.append(f"{field} = ?")
            params.append(value)
    if rule_id:
        conditions.append("instr(rule_ids, ?) > 0")
        params.append(f"|{rule_id}|")
    if query:
        conditions.append("(instr(lower(title), lower(?)) > 0 OR instr(lower(coalesce(node, '')), lower(?)) > 0)")
        params.extend([query, query])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with closing(sqlite3.connect(SCIEZKA_BAZY.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wykrycia'").fetchone():
            return result
        connection.execute("BEGIN")
        result["total"] = connection.execute("SELECT COUNT(*) FROM wykrycia" + where, params).fetchone()[0]
        rows = connection.execute(
            "SELECT finding_json FROM wykrycia" + where +
            " ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 "
            "WHEN 'low' THEN 3 ELSE 4 END, created_at DESC, finding_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        result["findings"] = [json.loads(row[0]) for row in rows]
    return result


def pobierz_wykrycie(finding_id: str) -> str | None:
    if not SCIEZKA_BAZY.is_file():
        return None
    with closing(sqlite3.connect(SCIEZKA_BAZY.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wykrycia'").fetchone():
            return None
        row = connection.execute("SELECT finding_json FROM wykrycia WHERE finding_id=?", (finding_id,)).fetchone()
    return row[0] if row else None


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


def pobierz_historie_raportow(
    *,
    limit: int = 25,
    offset: int = 0,
    host: str | None = None,
    unknown_host: bool = False,
    report_id_query: str | None = None,
    created_from: str | None = None,
    created_before: str | None = None,
) -> dict:
    """Odczyt historii bez tworzenia bazy i bez ładowania wszystkich raportów."""
    history = {
        "reports": [], "total": 0, "known_hosts": [], "known_host_count": 0,
        "latest_created_at": None, "limit": limit, "offset": offset,
    }
    if not SCIEZKA_BAZY.is_file():
        return history

    conditions = []
    parameters = []
    if host is not None:
        conditions.append("host = ?")
        parameters.append(host)
    if unknown_host:
        conditions.append("host IS NULL")
    if report_id_query:
        conditions.append("instr(lower(report_id), lower(?)) > 0")
        parameters.append(report_id_query)
    if created_from:
        conditions.append("julianday(created_at) >= julianday(?)")
        parameters.append(created_from)
    if created_before:
        conditions.append("julianday(created_at) < julianday(?)")
        parameters.append(created_before)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    order = " ORDER BY julianday(created_at) DESC, created_at DESC, report_id DESC"
    uri = SCIEZKA_BAZY.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        totals = connection.execute(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT host) AS hosts FROM raporty" + where,
            parameters,
        ).fetchone()
        history["total"] = totals["total"]
        history["known_host_count"] = totals["hosts"]
        history["known_hosts"] = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT host FROM raporty WHERE host IS NOT NULL ORDER BY host"
            )
        ]
        latest = connection.execute(
            "SELECT created_at FROM raporty" + where + order + " LIMIT 1", parameters
        ).fetchone()
        history["latest_created_at"] = latest[0] if latest else None
        rows = connection.execute(
            "SELECT report_id, created_at, host, raport_json FROM raporty"
            + where + order + " LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()

    for row in rows:
        report = json.loads(row["raport_json"])
        if not isinstance(report, dict) or not isinstance(report.get("tresc", {}), dict):
            raise ValueError("Niepoprawna struktura zapisanego raportu.")
        history["reports"].append({
            "report_id": row["report_id"],
            "created_at": row["created_at"],
            "host": row["host"],
            "liczba_zdarzen": report.get("liczba_zdarzen"),
            "podsumowanie": report.get("tresc", {}).get("podsumowanie", ""),
        })
    return history
