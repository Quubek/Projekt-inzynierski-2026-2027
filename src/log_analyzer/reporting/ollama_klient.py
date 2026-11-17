import json
import sqlite3
import os
from datetime import datetime, timezone
from uuid import uuid4

from httpx import TimeoutException
from ollama import Client, ResponseError
from pydantic import ValidationError

from log_analyzer.contracts import OpisRaportu, RaportZdarzen, UstrukturyzowanaTrescRaportu
from log_analyzer.reporting.input import prepare_report_input
from log_analyzer.reporting.prompt import PROMPT_VERSION, REPORT_MODEL, REPORT_SYSTEM_PROMPT
from log_analyzer.storage.sqlite_repo import (
    inicjalizuj_baze,
    pobierz_raport,
    zapisz_raport,
)

OpisModelu = OpisRaportu


class EmptyModelOutputError(ValueError):
    """Pusta odpowiedź jest błędem generatora, nie danych użytkownika."""


def generuj_opis_zdarzen(zdarzenia: list[dict], *, context: dict | None = None) -> UstrukturyzowanaTrescRaportu:
    if not zdarzenia:
        raise ValueError("Lista zdarzeń jest pusta.")

    prepared = prepare_report_input(zdarzenia, context)
    dane_zdarzen = json.dumps(prepared.payload, ensure_ascii=False, separators=(",", ":"))

    schemat = OpisModelu.model_json_schema()
    prompt = (
        REPORT_SYSTEM_PROMPT + "\nSchemat JSON odpowiedzi:\n"
        + json.dumps(schemat, ensure_ascii=False)
        )

    client = Client(
        host=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        timeout=120.0,
    )

    response = client.chat(
        model=REPORT_MODEL,
        messages=[
            {
                "role": "system",
                "content": prompt,
            },
            {"role": "user", "content": dane_zdarzen},
        ],
        format=schemat,
        stream=False,
        options={
            "num_ctx": 8192,
            "temperature": 0.1,
        },
    )

    opis = response.message.content

    if not opis or not opis.strip():
        raise EmptyModelOutputError("Model zwrócił pustą odpowiedź.")

    content = OpisModelu.model_validate_json(opis)
    return UstrukturyzowanaTrescRaportu(
        **content.model_dump(),
        kluczowe_zdarzenia=[f"{event['event_id']}: {event['raw']}" for event in zdarzenia],
    )

def generuj_raport(zdarzenia: list[dict], *, context: dict | None = None) -> RaportZdarzen:
    if not zdarzenia:
        raise ValueError("Lista zdarzeń jest pusta.")

    event_ids = [zdarzenie["event_id"] for zdarzenie in zdarzenia]

    if len(set(event_ids)) != len(event_ids):
        raise ValueError("Identyfikatory zdarzeń nie mogą się powtarzać.")

    hosty = {zdarzenie.get("host") for zdarzenie in zdarzenia}

    host = next(iter(hosty)) if len(hosty) == 1 else None

    czasy = [
        datetime.fromisoformat(zdarzenie["timestamp"])
        for zdarzenie in zdarzenia
        if zdarzenie.get("timestamp") is not None
    ]

    if any(czas.tzinfo is None for czas in czasy):
        raise ValueError("Czas zdarzenia musi zawierać strefę czasową.")

    czasy = [czas.astimezone(timezone.utc) for czas in czasy]

    prepared = prepare_report_input(zdarzenia, context)
    tresc = generuj_opis_zdarzen(zdarzenia, context=context)
    
    return RaportZdarzen(
        report_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        event_ids=event_ids,
        host=host,
        hosts=sorted(value for value in hosty if value),
        liczba_zdarzen_bez_hosta=sum(not event.get("host") for event in zdarzenia),
        liczba_zdarzen=len(zdarzenia),
        liczba_zdarzen_bez_czasu=len(zdarzenia) - len(czasy),
        czas_od=min(czasy) if czasy else None,
        czas_do=max(czasy) if czasy else None,
        tresc=tresc,
        czas_zrodlowy_od=min((event["timestamp_local"] for event in zdarzenia if event.get("timestamp_local")), default=None),
        czas_zrodlowy_do=max((event["timestamp_local"] for event in zdarzenia if event.get("timestamp_local")), default=None),
        llm_input_mode=prepared.mode, llm_event_ids=prepared.event_ids,
        llm_omitted_events=len(zdarzenia) - len(prepared.event_ids),
        prompt_version=PROMPT_VERSION, llm_model=REPORT_MODEL,
    )


def main() -> None:
    # Przykladowe zdarzenia do sprawdzenia generatora.
    zdarzenia = [
        {
            "event_id": "test-001",
            "timestamp": None,
            "host": "server01",
            "raw": "Failed password for admin from 192.0.2.10 port 51234 ssh2",
        },
        {
            "event_id": "test-002",
            "timestamp": None,
            "host": "server01",
            "raw": "Failed password for admin from 192.0.2.10 port 51235 ssh2",
        },
    ]
    
    inicjalizuj_baze()

    raport = generuj_raport(zdarzenia)
    zapisz_raport(raport.model_dump_json())

    print(f"\nZapisano raport: {raport.report_id}")

    zapisany_json = pobierz_raport(str(raport.report_id))

    if zapisany_json is None:
        raise RuntimeError("Nie znaleziono zapisanego raportu.")

    odczytany_raport = RaportZdarzen.model_validate_json(zapisany_json)

    if odczytany_raport != raport:
        raise RuntimeError("Odczytany raport różni się od zapisanego.")

    print("\nRaport odczytany z SQLite:")
    print(odczytany_raport.model_dump_json(indent=2))
    print("\nZapis i odczyt poprawne — raporty są identyczne.")


if __name__ == "__main__":
    try:
        main()
    except ConnectionError:
        raise SystemExit(
            "Nie można połączyć się z Ollamą. Uruchom ją i spróbuj ponownie."
        )
    except TimeoutException:
        raise SystemExit(
            "Przekroczono czas oczekiwania na odpowiedź Ollamy."
        )
    except ResponseError as blad:
        raise SystemExit(f"Ollama zwróciła błąd: {blad}")
    except ValidationError as blad:
        raise SystemExit(
            f"Dane nie są zgodne ze strukturą raportu:\n{blad}"
        )
    except ValueError as blad:
        raise SystemExit(f"Błąd danych: {blad}")
    except sqlite3.Error as blad:
        raise SystemExit(f"Błąd bazy SQLite: {blad}")
