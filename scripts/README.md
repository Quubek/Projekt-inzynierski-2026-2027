# Baseline detekcji HD

## Szybki start na macOS

Z katalogu głównego repozytorium uruchom:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scripts/requirements.txt
python scripts/make_synthetic.py
DATA_SOURCE=synthetic DATASET_NAME=synthetic-demo python scripts/train.py \
  --model-out artifacts/demo-baseline.joblib
```

Skrypt tworzy deterministyczny zbiór demonstracyjny, dzieli przykłady na
train/test, uczy pipeline TF-IDF + regresję logistyczną i zapisuje:

- model demonstracyjny i metadane w `artifacts/` (żeby nie zastępować modelu
  przeznaczonego do uruchomienia w API);
- metryki testowe w `reports/training_metrics_*.json`.

Raport obejmuje Precision, Recall, F1, Accuracy, ROC AUC, Average Precision,
raport klas i macierz pomyłek dla zbioru testowego.

```bash
DATA_SOURCE=synthetic DATASET_NAME=synthetic-demo python scripts/train.py \
  --model-out artifacts/demo-baseline.joblib
```

Dashboard odczytuje zapisane metryki przez API. Przy działającym Compose plik w
`reports/` jest widoczny w kontenerze API; odśwież widok **Ocena modeli**.
Pojedynczą predykcję dla tekstu `Features` można wykonać poleceniem:

```bash
python scripts/predict.py '[E5,E22,E11]' --model artifacts/demo-baseline.joblib
```

Wynik zawiera klasę anomalii, jej prawdopodobieństwo i wersję modelu.

## Trening na etykietowanym HDFS_v1

Z surowego `HDFS.log` i pliku etykiet z kolumnami `BlockId,Label` przygotuj
cechy zgodne z adapterem API:

```bash
python scripts/prepare_hdfs_features.py \
  --log /sciezka/do/HDFS.log \
  --labels /sciezka/do/anomaly_label.csv
DATA_SOURCE=loghub DATASET_NAME=HDFS_v1 python scripts/train.py
```

Po treningu skrypt zapisze `models/baseline.joblib`, metryki w
`reports/training_metrics_*.json` i metadane w `models/model_metadata.json`.
Model jest wymagany przez API; metryki dashboard odczyta z `reports/`.
Szczegóły kontraktu są w [models/README.md](../models/README.md).

Skrypt zachowuje tekst sesji dla każdego BlockID. Wiersz trafia do pierwszego
BlockID wykrytego w jego treści, zgodnie z przygotowaniem danych użytym do
bieżącego modelu. Etykiety Normal/Anomaly pochodzą z pliku HDFS_v1.

## Format danych po przygotowaniu

Trening oczekuje dwóch plików:

- `data/preprocessed/Event_traces.csv` z kolumnami `BlockId` i `Features`;
- `data/preprocessed/anomaly_label.csv` z kolumnami `BlockId` i `Label`, gdzie
  `Label` to `Normal` albo `Anomaly`.

Każdy `BlockId` musi wystąpić dokładnie raz w każdym pliku, a zbiory ID muszą
być zgodne. Uruchomienie na przygotowanych danych Loghub:

```bash
DATA_SOURCE=loghub DATASET_NAME=HDFS_v1 python scripts/train.py
```

Podziały są stratyfikowane i powtarzalne (seed 42). TF-IDF jest dopasowywane
wyłącznie do treningu. Ścieżki można zmienić przez `--data-dir`, `--model-out`,
`--metrics-out` i `--metadata-out`.

## Zakres modelu

Model przyjmuje sklejony tekst surowych linii sesji BlockID. Skrypt przygotowania
danych i API odtwarzają ten sam format; identyfikatory Drain3 nie są cechami
modelu. Wyniki syntetyczne służą wyłącznie do sprawdzenia przepływu. Model do
analizy logów należy trenować na etykietowanym HDFS_v1.

`scripts/check.py` dotyczy wcześniejszego wariantu train/val/test i wymaga
`models/split_val.csv`. Obecny trening tworzy train/test, więc do pojedynczego
sprawdzenia predykcji użyj `scripts/predict.py` zgodnie z instrukcją powyżej.
Nie zastępuj brakującego podziału walidacyjnego zbiorem testowym.
