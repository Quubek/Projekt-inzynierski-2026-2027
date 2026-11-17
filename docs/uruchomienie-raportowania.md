# Uruchomienie modułu raportowania — JF

Moduł generuje raport na podstawie przykładowych zdarzeń,
zapisuje go w SQLite i umożliwia odczyt po identyfikatorze.

Generator CLI korzysta z przykładowych zdarzeń zdefiniowanych w kodzie.
Można też wygenerować raport z grupy logów przesłanych przez API i dashboard —
opisuje to [instrukcja dashboardu](uruchomienie-dashboardu.md).
Detektor anomalii nie jest jeszcze podłączony.

## Wymagania

- Python 3.12.
- Zainstalowana Ollama.
- Model `qwen3:4b-instruct`.

Wszystkie poniższe polecenia wykonujemy w PowerShell,
z głównego folderu projektu.

## Przygotowanie środowiska

Jeśli folder `.venv` jeszcze nie istnieje:

```powershell
python -m venv .venv
```

Instalacja wymaganych bibliotek:

```powershell
.\.venv\Scripts\python.exe -m pip install ollama "pydantic>=2,<3" httpx
```

SQLite jest dostępne w standardowej bibliotece Pythona
i nie wymaga osobnej instalacji.

Uruchom aplikację Ollama. Jeśli model nie został jeszcze pobrany:

```powershell
ollama pull qwen3:4b-instruct
```

## Generowanie i zapis raportu

Wskaż folder zawierający pakiet projektu:

```powershell
$env:PYTHONPATH = "$PWD\src"
```

Polecenie wykonujemy ponownie po otwarciu nowego terminala.

Uruchom generator:

```powershell
.\.venv\Scripts\python.exe -m log_analyzer.reporting.ollama_klient
```

Program:
1. Pobiera przykładowe zdarzenia z funkcji `main()`.
2. Wysyła dane do lokalnej Ollamy.
3. Waliduje strukturę odpowiedzi przez Pydantic.
4. Dodaje metadane i oryginalne logi.
5. Zapisuje raport w SQLite.
6. Odczytuje zapisany raport i porównuje go z oryginałem.

Baza powstaje automatycznie w lokalizacji:

```text
runtime/raporty.sqlite3
```

Każde poprawne uruchomienie dodaje raport z nowym identyfikatorem.

## Uporządkowana treść raportu

Nowe raporty używają `tresc.schema_version: 2`. Model zwraca osobne pola:

- `obserwacja` — najważniejsze fakty wynikające z przekazanych danych;
- `powod_wskazania` — wyjaśnienie reguły/modelu albo informacja o ręcznym opisie bez detekcji;
- `ograniczenia_oceny` — lista konkretnych ograniczeń (może być pusta);
- `zalecenia` — lista dwóch lub trzech czynności weryfikacyjnych.

Dashboard wyświetla stałe sekcje: Obserwacja, Powód wskazania, Ograniczenia oceny
i Zalecane sprawdzenia. Nagłówki i numerację zapewnia aplikacja, a nie tekst modelu.
Lista `kluczowe_zdarzenia` nadal powstaje z oryginalnych logów w Pythonie.

Instrukcja systemowa jest w `src/log_analyzer/reporting/prompt.py`.
Logi są przesyłane osobno jako dane użytkownika, a model otrzymuje schemat czterech pól.
Nowe raporty zapisują `prompt_version` i `llm_model`, ułatwiając porównanie wyników.
Temperatura pozostaje 0.1, kontekst 8192, a model to `qwen3:4b-instruct`.

Starsze raporty z polami `podsumowanie` i `rekomendacja` są nadal odczytywane
w oryginalnym układzie, bez przepisywania danych w SQLite. Historia prezentuje
obserwację dla nowych raportów, a wcześniejsze podsumowanie dla starych.

## Odczyt istniejącego raportu

Skopiuj identyfikator z komunikatu `Zapisano raport`
lub z kolumny `report_id` w bazie.

Uruchom poniższe polecenie, zastępując `TWOJE_ID`
właściwym identyfikatorem:

```powershell
.\.venv\Scripts\python.exe -m log_analyzer.reporting.odczytaj_raport TWOJE_ID
```

Odczyt wymaga istniejącej bazy, ale nie wymaga uruchomionej Ollamy.

## Uruchomienie przez Docker Compose

Przygotowana konfiguracja korzysta z Docker Desktop na Windowsie
z kontenerami Linux. Ollama i model `qwen3:4b-instruct` pozostają
na komputerze gospodarza. Uruchom Docker Desktop i Ollamę.

Z głównego folderu projektu sprawdź konfigurację:

```powershell
docker compose config
```

Zbuduj obraz i uruchom generator:

```powershell
docker compose run --rm --build reporting
```

Generator kończy działanie po zapisaniu i odczytaniu raportu.
Opcja `--rm` usuwa zakończony kontener. Folder `runtime` jest
podłączony do `/app/runtime`, dlatego raporty pozostają w tej samej
lokalnej bazie po usunięciu kontenera.

Aby odczytać raport z nowego kontenera, zastąp `TWOJE_ID`
identyfikatorem zapisanym w bazie:

```powershell
docker compose run --rm reporting python -m log_analyzer.reporting.odczytaj_raport TWOJE_ID
```

Odczyt nie wymaga uruchomionej Ollamy. Przy korzystaniu z Dockera
nie trzeba aktywować lokalnej `.venv` ani ustawiać `PYTHONPATH`.
Po zmianach kodu ponownie zbuduj obraz, używając opcji `--build`.

Adres Ollamy jest odczytywany ze zmiennej `OLLAMA_URL`.
Domyślnie wynosi `http://localhost:11434`, a Compose ustawia
`http://host.docker.internal:11434` do połączenia z Windows.

## Pliki modułu

- `src/log_analyzer/reporting/ollama_klient.py` —
  generowanie raportu i przykład uruchomienia.
- `src/log_analyzer/contracts.py` — wspólne modele Pydantic.
- `src/log_analyzer/reporting/service.py` — raportowanie grupy z zapisanej analizy API.
- `src/log_analyzer/reporting/odczytaj_raport.py` —
  odczyt raportu po identyfikatorze.
- `src/log_analyzer/storage/sqlite_repo.py` —
  tworzenie tabeli, zapis i odczyt danych.
- `docker/Dockerfile.reporting` — środowisko kontenera generatora.
- `compose.yaml` — konfiguracja uruchomienia i podłączenia bazy.
- `.dockerignore` — pliki pomijane przy budowaniu obrazu.

## Dotychczasowa weryfikacja ręczna

Potwierdzono:
- generowanie i zapis raportu przy uruchomionej Ollamie;
- zgodność raportu odczytanego z bazy z zapisanym;
- odczyt wcześniejszego raportu po zakończeniu generatora
  i wyłączeniu Ollamy;
- czytelny komunikat przy próbie generowania z wyłączoną Ollamą;
- generowanie, zapis i odczyt raportu w kontenerze Docker Compose.

Obsługa pozostałych błędów wymaga osobnego sprawdzenia.

## Ograniczenia

Walidacja Pydantic sprawdza strukturę danych.
Nie gwarantuje poprawności merytorycznej opisu ani rekomendacji LLM.

Metadane raportu i lista kluczowych zdarzeń są tworzone w Pythonie.
Obserwacja, powód wskazania, ograniczenia oceny i zalecenia pochodzą z modelu.
Poprawny schemat i stały układ nie gwarantują poprawności tych treści;
ich jakość wymaga osobnej oceny na przygotowanych przypadkach.

Baza w folderze `runtime/` jest pomijana przez Git.
Każdy członek zespołu tworzy własną lokalną bazę.
