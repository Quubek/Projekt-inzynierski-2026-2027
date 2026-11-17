# Integracja JB / JF / HD

## Działająca ścieżka API i raportowania

1. Dashboard wysyła logi do `POST /api/v1/analyze`.
   Dla pliku przeglądarka wysyła surową treść do `POST /api/v1/analyze/file`:
   odbiór fragmentami, do 2 GiB, maksymalnie 10 000 niepustych wpisów.
   Import nie przechodzi przez pamięć `st.file_uploader`; oba wejścia tworzą `AnalyzeRequest`.
2. Parser JB normalizuje wpisy, wydobywa szablony Drain3 i tworzy grupy.
3. API zapisuje wynik w tabeli `analizy` w `runtime/raporty.sqlite3`.
4. Użytkownik wybiera grupę lub wskazanie reguły i uruchamia raport przez
   `POST /api/v1/analyses/{analysis_id}/reports`, wysyłając `group_id` albo `finding_id`.
5. Serwis `reporting/service.py` odczytuje oryginalne zdarzenia grupy i wywołuje
   `generuj_raport` JF. Przeglądarka nie przekazuje własnych źródeł raportu.
6. Generator wywołuje lokalną Ollamę, waliduje odpowiedź i zachowuje oryginalne logi.
7. Raport trafia do SQLite; dashboard otwiera ten sam widok szczegółów co historia.

Raport zawiera `analysis_id`, `group_id` i `generation_mode: "manual"`.
Identyfikatory, host i czas pochodzą z danych, a nie z decyzji LLM.
Brak czasu lub hosta pozostaje brakiem danych. Obecne grupy SSH dotyczą jednego hosta,
a parser HDFS nie wyznacza hosta. Generator nadal wymaga jednej wartości pola `host`
w grupie (może to być `null`).

Bez artefaktu `models/baseline.joblib` detekcja ML ma status `not_configured`.
Po dodaniu zgodnego modelu API zapisuje wyniki ML obok reguł HDFS w `findings`.
Reguły mają osobny `rules_status`.
Utworzenie raportu nie oznacza wykrycia anomalii.
`reporting_status: "not_run"` opisuje etap automatycznego pipeline'u analizy;
raport jest obecnie uruchamiany osobnym żądaniem użytkownika.

Przeglądanie raportów działa bez Ollamy. Błąd Ollamy nie usuwa zapisanej analizy.
Wejście LLM ograniczono do 20 oryginalnych przykładów i 6000 bajtów JSON.
Przy większej liczbie danych generator tworzy agregaty wszystkich zdarzeń oraz dobiera
przykłady, jawnie zapisując `llm_input_mode`, `llm_event_ids` i `llm_omitted_events`.
Pełne oryginalne logi są w raporcie i bazie. LLM generuje obserwację, powód wskazania,
listę ograniczeń i listę zaleceń, walidowane przez `OpisRaportu`;
listę źródeł tworzy Python. Pojedynczy wpis, który nie mieści się w wejściu, nie jest przycinany.

Wersja prompta `log-report-v2` definiuje role, zasady interpretacji i cztery sekcje treści.
Instrukcja systemowa i dane logów są oddzielnymi wiadomościami. Raport zapisuje wersję
prompta i model, a `tresc.schema_version` wynosi 2. Odczyt wspiera również dawny format
dwóch pól tekstowych, bez migracji istniejących zapisów w SQLite.

## Reguły HDFS i jakość danych

`NormalizedEvent` zawiera opcjonalne `source_ip`, `destination_ip`, `node_ip`, `target_ip`
oraz listę `other_ips`. Moduł `parsing/addresses.py` przypisuje role na podstawie
rozpoznanych komunikatów, walidując literały przez `ipaddress`. Drain3 nadal odpowiada
za szablony, a nie za ustalanie ról IP. Nieznana rola nie jest zgadywana.
Adresat polecenia HDFS nie jest utożsamiany z celem transmisji bloku.
Dashboard potrafi odtworzyć role starszych analiz z parametrów i źródłowej treści,
bez migracji zapisów. Definicje reguł w katalogu pochodzą z tego samego modułu
`detection/catalog.py` co detektor; katalog nie zmienia historycznych opisów reguł.

Reguły są w `src/log_analyzer/detection/rules.py`. To demonstracyjne warunki do walidacji:

- `HDFS-001`: wyjątki `Got exception while serving`, łączone według węzła.
- `HDFS-002`: co najmniej 3 takie wyjątki jednego węzła w oknie 300 sekund.
  Wyjątki objęte serią nie tworzą dodatkowego, powielonego wskazania HDFS-001.
- `HDFS-003`: pojedyncze żądanie usunięcia co najmniej 50 różnych bloków.
  Jedno polecenie tworzy jedno wskazanie, niezależnie od liczby BlockID.

Priorytety są wstępne (niski dla HDFS-001/003, średni dla serii HDFS-002).
Żadne wskazanie nie jest potwierdzeniem ataku lub awarii. Zwykłe `Deleting block`
i `PacketResponder ... terminating` nie uruchamiają tych reguł.
Reguły nie są stosowane do SSH. Kompletność sekwencji jest nieznana, o ile nie zadeklarowano inaczej;
ta wersja nie ocenia brakujących zakończeń operacji.

Parser zachowuje czas lokalny w `timestamp_local`. `timestamp` zawiera UTC tylko po
odczytaniu jawnej strefy z logu lub zastosowaniu zadeklarowanej strefy źródła.
SSH bez roku wymaga `source_year`, aby wyznaczyć pełny czas. Nie zgaduje się roku.
Przy niejednoznaczności zmiany czasu UTC pozostaje puste z odpowiednią uwagą.

Nowe analizy i wskazania są zapisywane w jednej transakcji w SQLite. Lista wykryć
korzysta z filtrowania i stronicowania SQL. Brak tabeli wykryć w starszej bazie daje pustą listę.

Odczyt dostarczonego `HDFS_2k.log` bez podłączonego artefaktu ML dał 2000 wpisów, 80 WARN, 2200 BlockID i 66 wskazań
(64 połączone zbiory wyjątków oraz 2 żądania usunięcia po 100 bloków).
To wynik działania reguł na próbce, a nie pomiar Precision/Recall ani liczba potwierdzonych anomalii.

## Kolejne kroki

- Ocena predykcji na odpowiednich, kompletnych sekwencjach HDFS; fragmenty logów nie zastępują zbioru oceny jakości.
- Stronicowanie zdarzeń po stronie API oraz zadania importu w tle, jeśli będą potrzebne.
  Obecnie odbiór pliku jest strumieniowy, ale analiza obejmuje ograniczoną paczkę do 10 000 wpisów.
- Walidacja reguł, progów i jakości raportów na odpowiednich danych.

## Uruchomienie

Zainstaluj zależności API i dashboardu, następnie uruchom oba procesy zgodnie z
[instrukcją dashboardu](uruchomienie-dashboardu.md). Po aktualizacji kodu zrestartuj
API. Ollama ma działać z modelem `qwen3:4b-instruct`.

Przy Docker Desktop:

```powershell
docker compose up --build api dashboard
```

API ma ustawiony adres Ollamy `http://host.docker.internal:11434`.
Lokalnie domyślny adres to `http://localhost:11434`; można go zmienić przez `OLLAMA_URL`.

## Wyniki HD w dashboardzie

Baseline HD `scripts/train.py` zapisuje wyniki do `reports/training_metrics_*.json`;
API odczytuje najnowszy plik z tego katalogu albo wskazany `EVALUATION_RESULTS_PATH`.
Macierz pomyłek ma kolejność klas `[0, 1]`: 0 — normalne, 1 — anomalie;
wiersze oznaczają klasy rzeczywiste, kolumny przewidziane.
Dashboard pokazuje Precision, Recall, F1, Accuracy, ROC AUC i AP, jeśli są
dostępne, oraz metryki klas wyliczone z macierzy. Główny zestaw dotyczy klasy 1.
Instrukcja uruchomienia baseline'u:
[scripts/README.md](../scripts/README.md).

Przed treningiem na przygotowanych danych syntetycznych HD ustawia:

```powershell
$env:DATA_SOURCE = "synthetic"
$env:DATASET_NAME = "synthetic-demo"
python scripts/train.py --model-out artifacts/demo-baseline.joblib
```

Na Ubuntu odpowiednikiem jest:

```bash
DATA_SOURCE=synthetic DATASET_NAME=synthetic-demo python scripts/train.py --model-out artifacts/demo-baseline.joblib
```

Dla rzeczywistego eksperymentu na Loghub ustaw `DATA_SOURCE=loghub` i dokładną nazwę
zbioru w `DATASET_NAME`. Brak ustawienia daje `unknown`, widoczne jako ostrzeżenie.
Sama etykieta źródła nie jest automatycznie weryfikowana — opisuje ją autor eksperymentu.

Dashboard odczytuje zapisane wyniki, nie uruchamia treningu ani oceny.
W Compose katalog `reports/` jest montowany do API. Można też wskazać konkretny
plik przez `EVALUATION_RESULTS_PATH`.

Obsługiwany jest płaski JSON eksportowany przez trening Colaba oraz format
zbiorczy z polem `experiments`. W wynikach Colaba dashboard pokazuje wyłącznie
metryki testowe dostępne w pliku. Porównuj modele oceniane na tym samym podziale.

## Artefakt i wejście detektora ML

`scripts/prepare_hdfs_features.py` tworzy treningowe cechy z surowego HDFS.log i
etykiet BlockID, a API liczy te same cechy z grupy zdarzeń. Model musi być
wytrenowany na tej reprezentacji; identyfikatory Drain3 nie są używane jako
cechy.

Wymagany artefakt to `models/baseline.joblib`, pipeline TF-IDF + LogisticRegression
z klasami `[0, 1]`. Skopiowanie go do
repozytorium aktywuje ocenę grup HDFS w API i dashboardzie. Wyniki są osobnymi
wskazaniami `source=ml`; grupa bez znanych cech jest pomijana i oznaczana jako
częściowo oceniona. Score `predict_proba` to wynik klasyfikatora, a nie
zweryfikowana pewność diagnozy. Opis nazw plików i kontraktu jest w
[models/README.md](../models/README.md).

Model należy trenować na etykietowanym HDFS_v1. Nie używaj wyniku reguł HDFS
jako etykiet. Predykcje ML pozostają niedostępne, jeśli zgodny artefakt nie
znajduje się pod skonfigurowaną ścieżką.

## Weryfikacja

Po scaleniu wersji HD i JF testy integracyjne sprawdzają również: wczytanie
testowego pipeline'u TF-IDF, predykcję grup HDFS, zapis wskazania `source=ml`,
generowanie raportu w schemacie 2 i odczyt z historii. Odpowiedź Ollamy jest
kontrolowana, model jest małym artefaktem utworzonym w katalogu testowym.
Osobny test odczytuje dostarczony plik metryk HD i sprawdza widok testowego F1
oraz macierz pomyłek. Testy nie odtwarzają treningu HD ani oceny zbioru testowego.
Dołączony `models/baseline.joblib` jest również wczytywany i sprawdzany przez API
na przykładach HDFS. Zależności modelu przypięto w `requirements-api.txt`.

Próba funkcjonalna na `HDFS_2k.log` z dołączonym modelem dała 2000 zdarzeń,
2200 grup, 1994 grupy z predykcją i 206 nieocenionych. Status `partial` wynika
z pominięcia grup bez zgodnych cech, m.in. wtórnych BlockID w wieloblokowych
poleceniach. Próbka zawiera niepełne sekwencje; liczba wskazań nie jest miarą
skuteczności i nie powinna być porównywana wprost z F1 pełnego zbioru HD.

Wskazanie ML zapisuje `details.group_id` i identyfikatory wpisów rzeczywiście
użytych do predykcji. Wpis wymieniający kilka bloków pozostaje widoczny
w ich grupach, ale jego cechy są używane tylko dla pierwszego BlockID.

Testy obejmują parsowanie, zapis analizy, wybór grupy, wygenerowanie raportu,
zapis i odczyt z historii oraz przejście w dashboardzie. W testach odpowiedź Ollamy
jest kontrolowana, a wszystkie bazy są tymczasowe. Testy obejmują też niedostępną
Ollamę, timeout, błędny JSON, nieznaną grupę i niepoprawne metryki.
