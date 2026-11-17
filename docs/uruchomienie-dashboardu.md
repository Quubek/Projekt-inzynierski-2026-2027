# Panel projektu — dashboard Streamlit

Dashboard przyjmuje logi do parsowania, pozwala ręcznie wygenerować raport z grupy
zdarzeń oraz wyświetla raporty zapisane w `runtime/raporty.sqlite3`.
Pobiera dane przez FastAPI; nie otwiera bazy bezpośrednio.
Ollama nie jest potrzebna do przeglądania i pobierania istniejących raportów.

## Docker Compose — zalecane uruchomienie

Uruchom Docker Desktop z kontenerami Linux. Z głównego folderu projektu:

```powershell
docker compose up --build api dashboard
```

Otwórz dashboard: <http://localhost:8501>.
Dokumentacja API jest dostępna pod <http://localhost:8000/docs>.

API korzysta z podłączonego folderu `runtime`, dlatego widoczne są też
raporty wygenerowane wcześniej lokalnie lub przez usługę `reporting`.
Dashboard nie wymaga montowania bazy. Zakończenie usług nie usuwa raportów.
Polecenie `docker compose down` zatrzymuje i usuwa kontenery usług.

Do generowania raportu z dashboardu uruchom Ollamę na laptopie z modelem
`qwen3:4b-instruct`. API w kontenerze łączy się z nią przez `host.docker.internal`.
Ollama nie jest uruchamiana przez Compose.

Opcjonalny generator CLI nadal pozwala dodać raport na podstawie przykładowych zdarzeń:

```powershell
docker compose run --rm --build reporting
```

Następnie kliknij **Odśwież** w dashboardzie.

## Uruchomienie lokalne bez Dockera

Wymagany Python 3.12 i środowisko `.venv` w głównym folderze projektu.
Jeśli nie istnieje, utwórz je poleceniem `python -m venv .venv`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt -r requirements-dashboard.txt
```

Terminal 1 — API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn log_analyzer.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Terminal 2 — dashboard, również z głównego folderu projektu:

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m streamlit run src/log_analyzer/dashboard/app.py
```

Domyślny adres API to `http://127.0.0.1:8000`. Można go zmienić przez
zmienną środowiskową `API_URL` w terminalu uruchamiającym Streamlit.
Motyw aplikacji znajduje się w `.streamlit/config.toml`.

## Obsługa

- Strona startowa zawiera kafelki prowadzące do osobnych widoków:
  Analiza logów, Wykrycia i anomalie, Historia raportów i Ocena modeli.
- Strona startowa ma tytuł **Analizator logów**, bez numerowania i etykiet dostępności kafelków.
  Obok kafelków sekcja **Jak działają reguły?** wyjaśnia ich rolę.
  Przycisk **Przeglądaj reguły** otwiera osobny **Katalog reguł**: ID, nazwę i pełny opis.
  Katalog umożliwia wyszukiwanie po tych polach i wyświetla do 25 reguł na stronie.
  Pogrubione nazwy reguł w szczegółach wykrycia i raporcie mają podpowiedź po najechaniu;
  kliknięcie rozwija pełny opis i identyfikator.
  Nowe wykrycia zapisują nazwę i opis użytej wersji reguły, aby historyczny raport zachował warunki analizy.
- Nawigacja odbywa się przez kafelki, bez lewego panelu. W pozostałych
  widokach przycisk **Powrót do startu** znajduje się w lewym górnym rogu.
- Analiza logów umożliwia wklejenie tekstu lub przesłanie pliku UTF-8 `.log`/`.txt`.
  Wklejanie tekstu: wybierz SSH lub HDFS i kliknij **Sprawdź logi** (do 2 MiB tekstu).
- Import pliku: wybierz **Prześlij plik**, ustaw źródło w formularzu i kliknij
  **Prześlij i przeanalizuj**. Formularz jest dostępny też w osobnej karcie pod `/import` API.
  Postęp dotyczy przesyłania; po nim API jeszcze parsuje i zapisuje analizę.
  Na końcu **Otwórz wynik analizy w dashboardzie** otwiera zapisany wynik.
- Limit pliku wynosi **2 GiB (2 147 483 648 bajtów, w UI: 2 GB / 2048 MiB)**.
  Jednocześnie obowiązuje **10 000 niepustych wpisów** i **10 000 znaków na wpis**.
  Duży plik może więc zostać odrzucony wcześniej ze względu na liczbę lub długość wpisów.
  Puste wiersze są pomijane. Przekroczenie któregokolwiek limitu odrzuca całą paczkę;
  aplikacja nie obcina danych i nie zapisuje częściowej analizy.
- Plik trafia bezpośrednio z przeglądarki do `POST /api/v1/analyze/file`, bez
  `st.file_uploader` i bez kopiowania całego pliku do tekstu lub JSON w Streamlit.
  API czyta fragmentami, sprawdza rzeczywistą liczbę bajtów także bez `Content-Length`,
  dekoduje UTF-8 (również BOM, CRLF i CR) i przechowuje tylko ograniczoną listę wpisów.
  Cały zaakceptowany wynik jest nadal analizowany i przechowywany w pamięci przed zapisem.
  Nie jest to przetwarzanie nieograniczonego zbioru ani zadanie działające w tle.
- Wklejany tekst korzysta z istniejącego `POST /api/v1/analyze`. Obie ścieżki używają
  tego samego parsera, reguł i zapisu. Wynik zawiera
  uporządkowane zdarzenia, grupy, wskazania reguł HDFS oraz uwagi API.
  Model ML nadal nie jest podłączony. Reguły wskazują zachowania do sprawdzenia.
- W **Informacjach o źródle** można podać strefę IANA, np. `Europe/Warsaw` albo `UTC`,
  oraz rok dla logów SSH bez roku. Nie uzupełnia się ich strefą laptopa ani bieżącym rokiem.
  Jawna strefa z logu ma pierwszeństwo. Nieistniejący lub niejednoznaczny czas lokalny
  podczas zmiany czasu nie jest automatycznie przeliczany na UTC.
- Można zadeklarować, czy dane są próbką, pełnym zapisem, czy nie wiadomo.
  Deklaracja nie stanowi automatycznej weryfikacji kompletności śladów.
- Filtry zdarzeń obejmują poziom logu, komponent, fragment treści/BlockID, datę źródłową
  oraz osobno IP źródłowe, docelowe i IP w dowolnej roli. Filtry łączą się warunkiem „i”.
  Można wybrać **Nie ustalono** dla brakującej roli lub **Brak adresów IP** dla całego wpisu.
  Tabela pokazuje IP źródłowe, docelowe i pozostałe; pełny komunikat znajduje się w szczegółach.
  Po wybraniu wiersza dostępne są oryginalny log, role adresów, parametry i powiązane bloki.
  Role wynikają z rozpoznanych komunikatów SSH/HDFS, a nie z decyzji LLM czy samego maskowania Drain3.
  Źródło i cel dotyczą transmisji opisanej w logu. Adresat polecenia HDFS oraz węzeł są osobnymi rolami.
  Nazwa hosta nie jest automatycznie zamieniana na IP; adresy o nieznanej roli pozostają pozostałymi IP.
  Brak roli nie oznacza braku połączenia. Starsze analizy korzystają z zachowanych parametrów i treści,
  bez przepisywania bazy. Parser obsługuje IPv4 HDFS i literały IPv4/IPv6 w rozpoznanych logowaniach SSH.
  Uwagi wynikają z braków danych; informacje o identyfikatorach Drain3 są w diagnostyce.
- Wynik ostatniego parsowania pozostaje w sesji przy przechodzeniu między widokami.
  Błąd kolejnej próby usuwa poprzedni wynik, aby nie pomylić paczek danych.
- Po parsowaniu wybierz grupę i kliknij **Generuj raport**, a następnie **Otwórz raport**.
  API pobiera zdarzenia z zapisanej analizy, wywołuje Ollamę, waliduje i zapisuje raport.
  Ręczny wybór grupy nie jest wynikiem detekcji anomalii.
- Wejście LLM obejmuje do 20 oryginalnych przykładów i 6000 bajtów JSON danych wejściowych.
  Nie powiela szablonu ani listy bloków z pełnego obiektu zdarzenia.
  Większe zestawy są agregowane, z jawną listą przykładów i liczbą pominiętych oryginałów.
  Raport nadal zachowuje wszystkie identyfikatory i pełne źródła. Tryb agregacji jest widoczny
  w podglądzie i JSON. Zbyt długi pojedynczy wpis jest odrzucany, bez cichego przycinania.
  Kontekst Ollamy wynosi 8192 tokeny, a czas oczekiwania generatora — 120 sekund.
- Brak połączenia z Ollamą lub błędna odpowiedź nie usuwa analizy ani nie zapisuje raportu.
  **Wykonane:** ręcznie sprawdzono komunikat po wyłączeniu Ollamy oraz ponowne generowanie
  i zapis po jej uruchomieniu. To sprawdzenie obsługi błędu, nie ocena jakości treści LLM.
- Detekcja wymaga jeszcze funkcji predykcji HD i zgodnego przygotowania cech.
- **Wykrycia i anomalie** pokazuje zapisane sygnały z reguł, sortowane według priorytetu,
  z filtrami po analizie, regule, priorytecie i nazwie/adresie węzła. Lista jest stronicowana po 25.
  Szczegóły pokazują uzasadnienie, wartości progów, oryginalne logi i pobieranie źródeł JSON.
  Można wygenerować raport wykrycia i wrócić do niego ze szczegółów raportu.
  Nie ma statusów ręcznego przeglądu typu „Nowe”/„Zamknięte”.
- **Ocena modeli** odczytuje plik `runtime/evaluation/results.json` przez API.
  Wyświetla Precision, Recall, F1 i macierz pomyłek oraz pochodzenie danych.
  Brak pliku daje pusty widok, a nie przykładowe metryki. Szczegóły w
  [instrukcji integracji](integracja-modulow.md).
- Historia jest uporządkowana od najnowszego raportu, po 25 wpisów na stronie.
- Filtry obejmują host, brak danych o hoście, fragment ID oraz datę utworzenia.
- Obie graniczne daty w interfejsie obejmują całe wybrane dni w UTC.
- Liczniki dotyczą całego wyniku filtrowania, a nie tylko widocznej strony.
- Zaznacz wiersz i kliknij **Otwórz raport**, aby przejść do osobnego ekranu.
- Szczegóły mają zakładki: Podsumowanie, Zdarzenia źródłowe i Dane raportu.
- W nowych raportach zakładka Podsumowanie ma stałe sekcje: Obserwacja,
  Powód wskazania, Ograniczenia oceny i Zalecane sprawdzenia. Zalecenia są numerowane przez UI.
  Starsze raporty zachowują oryginalne podsumowanie i rekomendację.
  W metadanych nowych raportów widnieją wersja prompta i model użyty do generowania.
- Przycisk **Wróć do historii** zachowuje filtry oraz wybraną stronę listy.
- Raport można też otworzyć przez adres `?view=report&report_id=IDENTYFIKATOR`.
  Ta sama ścieżka będzie wykorzystywana przez przyszły widok analizy.
- Przycisk **Pobierz JSON** pobiera pełny raport z zachowaniem polskich znaków.
- Brak bazy daje pustą historię. Sam odczyt nie tworzy bazy ani raportów.

Czas utworzenia raportu jest oddzielony od czasu zdarzeń. Brakujące dane
są oznaczane jako brak danych. Poziom logu, priorytet reguły i wynik ML są osobnymi informacjami.
Priorytety reguł są wstępne, a wynik ML pozostaje niedostępny do podłączenia detektora.
Opisy i rekomendacje LLM wymagają oceny analityka.

## Endpoint historii

`GET /api/v1/reports` zwraca `reports`, `total`, `known_hosts`,
`known_host_count`, `latest_created_at`, `limit` i `offset`.

Parametry opcjonalne:

- `limit`: 1–100, domyślnie 25; `offset`: od 0.
- `host`: dokładna nazwa; `unknown_host=true`: raporty bez hosta.
- `report_id_query`: fragment identyfikatora, bez rozróżniania wielkości liter.
- `created_from`: początek włącznie; `created_before`: koniec wyłącznie.
  Daty API muszą zawierać strefę czasową.

Przykład: <http://localhost:8000/api/v1/reports?limit=25&offset=0>.
Odczyt szczegółów: `GET /api/v1/reports/{report_id}`.

## Endpointy integracji

- `POST /api/v1/analyze` — parsuje i zapisuje analizę.
- `POST /api/v1/analyze/file` — przyjmuje surowe bajty pliku w treści HTTP (bez multipart),
  `Content-Type: application/octet-stream`. Parametry query: `log_format`, `source_timezone`,
  `source_year`, `data_scope`, takie jak dla JSON. Zwraca małe potwierdzenie:
  `analysis_id`, `event_count`, `finding_count`; pełny wynik pobiera się osobnym GET.
  Przekroczenie rozmiaru: HTTP 413; błędne dane, kodowanie lub liczba wpisów: HTTP 422.
- `GET /api/v1/analyses/{analysis_id}` — odczytuje zapisaną analizę.
- `POST /api/v1/analyses/{analysis_id}/reports` — przyjmuje `{"group_id": "..."}`
  albo `{"finding_id": "UUID"}` (dokładnie jedno źródło)
  i zwraca zapisany raport (HTTP 201). Wymaga Ollamy.
- `GET /api/v1/findings` — stronicowana lista, filtry: `analysis_id`, `priority`, `rule_id`, `query`.
- `GET /api/v1/findings/{finding_id}` — szczegóły zapisanego wskazania.
- `GET /api/v1/evaluation` — odczytuje wyniki eksperymentów HD.

Analizy i raporty znajdują się w tej samej bazie, w osobnych tabelach.
Tabele analiz i wykryć są tworzone automatycznie, bez usuwania wcześniejszych raportów.
Stare analizy nie są automatycznie przeliczane; prześlij logi ponownie, aby uruchomić reguły.

Formularz importu działa w przeglądarce, dlatego potrzebuje adresów dostępnych z laptopa.
Domyślnie `API_PUBLIC_URL=http://localhost:8000` (dashboard → formularz),
`DASHBOARD_PUBLIC_URL=http://localhost:8501` (formularz → wynik w dashboardzie).
Compose ustawia oba adresy; `API_URL=http://api:8000` pozostaje adresem wewnętrznym usług.
Przy dostępie zdalnym ustaw odpowiednie publiczne adresy usług; ta zmiana nie wystawia
automatycznie portów Dockera poza localhost.

## Weryfikacja

Pełny zestaw testów obejmuje też predykcję baseline'u i wymaga bibliotek HD:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt -r requirements-dashboard.txt -r scripts/requirements.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest tests -q
```

Testy korzystają z tymczasowych baz i odpowiedzi testowych; nie wywołują
Ollamy ani nie zmieniają lokalnej historii raportów.
