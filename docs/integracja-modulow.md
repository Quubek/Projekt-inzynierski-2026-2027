# Integracja JB / JF / HD

## Działająca ścieżka API i raportowania

1. Dashboard wysyła logi do `POST /api/v1/analyze`.
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
Pełne oryginalne logi są w raporcie i bazie. LLM generuje tylko podsumowanie i rekomendację;
listę źródeł tworzy Python. Pojedynczy wpis, który nie mieści się w wejściu, nie jest przycinany.

## Reguły HDFS i jakość danych

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

Odczyt dostarczonego `HDFS_2k.log` dał 2000 wpisów, 80 WARN, 2200 BlockID i 66 wskazań
(64 połączone zbiory wyjątków oraz 2 żądania usunięcia po 100 bloków).
To wynik działania reguł na próbce, a nie pomiar Precision/Recall ani liczba potwierdzonych anomalii.

## Kolejne kroki

- Trening modelu HD na etykietowanym HDFS_v1 i walidacja wyników na danych testowych.
- Większe importy przetwarzane stopniowo i stronicowanie zdarzeń po stronie API.
  Obecny formularz nadal obsługuje do 2 MB i 5000 wpisów; ta zmiana nie udaje obsługi pełnego zbioru HDFS.
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

Testy obejmują parsowanie, zapis analizy, wybór grupy, wygenerowanie raportu,
zapis i odczyt z historii oraz przejście w dashboardzie. W testach odpowiedź Ollamy
jest kontrolowana, a wszystkie bazy są tymczasowe. Testy obejmują też niedostępną
Ollamę, timeout, błędny JSON, nieznaną grupę i niepoprawne metryki.
