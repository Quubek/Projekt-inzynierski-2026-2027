# Uruchomienie modułu raportowania — JF

Moduł generuje raport na podstawie przykładowych zdarzeń,
zapisuje go w SQLite i umożliwia odczyt po identyfikatorze.

Na obecnym etapie zdarzenia są zdefiniowane w kodzie.
Moduł nie jest jeszcze połączony z API ani detektorem anomalii.

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
  generowanie raportu, modele Pydantic i przykład uruchomienia.
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
Podsumowanie i rekomendacja pochodzą z modelu.

Baza w folderze `runtime/` jest pomijana przez Git.
Każdy członek zespołu tworzy własną lokalną bazę.
