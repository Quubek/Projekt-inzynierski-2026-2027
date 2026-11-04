# JB: pierwsza wersja API i parsowania logów

Stan: 4 listopada 2026. Prototyp przygotowany ze wsparciem asystenta AI.
Kod uruchomiono lokalnie i sprawdzono testami. Nie jest to jeszcze pełny system detekcji.

## Co działa

- `GET /health`: sprawdzenie dostępności API.
- `POST /api/v1/analyze`: JSON z listą logów, walidacja Pydantic, normalizacja
  nagłówka HDFS lub SSH, rozpoznawanie szablonów Drain3 i grupowanie po BlockID dla HDFS.
- `GET /api/v1/reports/{report_id}`: odczyt istniejącego raportu przez moduł SQLite JF.
- Automatyczna dokumentacja i formularz do prób pod `/docs`.
- Błędne dane zwracają HTTP 422, brak raportu HTTP 404.

Przykłady w `data/samples/` są małymi, ręcznie przygotowanymi danymi demonstracyjnymi.
Nie służą do oceny jakości klasyfikatora ani do potwierdzenia wykrycia ataku.

## Uruchomienie (PowerShell, z katalogu repozytorium)

Wymagany Python 3.11 lub nowszy. Lokalną demonstrację sprawdzono na Pythonie 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m uvicorn log_analyzer.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

W przeglądarce otwórz `http://127.0.0.1:8000/docs`.
W drugim terminalu uruchom:

```powershell
.\.venv\Scripts\python.exe scripts/demo_api.py
```

Testy:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
.\.venv\Scripts\python.exe -m pytest -q
```

## Przykład żądania

Skopiuj całe `data/samples/hdfs_request.json` do formularza endpointu w `/docs`.
Trzy wpisy tworzą dwie grupy BlockID. Dwa komunikaty `Receiving block` mają wspólny
szablon mimo innych identyfikatorów bloków i adresów IP.

`event_id` identyfikuje konkretny wpis. `template_id` oznacza typ komunikatu tylko
w obrębie bieżącej paczki. `group_id` dla HDFS jest identyfikatorem bloku.

## Ograniczenia i dalsze prace

1. Nie podłączono modelu HD: `detection_status` ma wartość `not_configured`.
   Skrypt `scripts/train.py` używa liczbowych cech z `Event_traces.csv`.
   Nowe ID Drain3 nie są automatycznie zgodne z tym słownikiem. Potrzebujemy
   wspólnej mapy szablonów, identycznego przygotowania cech i zapisanego modelu.
   W pobranej wersji main nie ma `predict.py` ani pliku modelu.
2. Nie wywołano automatycznie generatora JF. Po uzgodnieniu detekcji należy
   przekazać zdarzenia anomalii do generatora i zapisane raporty udostępnić przez API.
3. HDFS jest grupowany według BlockID, ponieważ model HD ocenia sekwencje.
   Podział jednej sekwencji między paczki wymaga późniejszej obsługi stanu.
4. Czas z logu bez strefy jest przechowywany jako `timestamp_raw`.
   `timestamp` pozostaje `null`. SSH nie podaje również roku.
   Host HDFS pozostaje `null`, ponieważ nagłówek go nie zawiera.
5. Miner Drain3 działa osobno dla każdego żądania. Trwały słownik szablonów
   i zgodność z treningiem są zadaniem integracyjnym na kolejny etap.
6. Grupowanie SSH po hoście jest tylko przykładem, bez okien czasowych.

## Źródła techniczne

- FastAPI, dane wejściowe: https://fastapi.tiangolo.com/tutorial/body/
- FastAPI, testy: https://fastapi.tiangolo.com/tutorial/testing/
- Drain3, dokumentacja i implementacja: https://github.com/logpai/Drain3

## Podział pracy

JB odpowiada za przyjęcie, uporządkowanie i przekazanie logów. HD odpowiada za
model i zgodność reprezentacji cech. JF odpowiada za generowanie i przechowywanie
raportów. Odczyt raportów w API korzysta z istniejącego modułu JF i nie oznacza
napisania przez JB własnego generatora lub warstwy bazy.
