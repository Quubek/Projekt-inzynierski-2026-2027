# Artefakt modelu ML

Compose montuje ten katalog do API tylko do odczytu. Wersjonowany artefakt
modelu znajduje się pod nazwą:

```text
models/baseline.joblib
```

Obsługiwany jest artefakt scikit-learn `Pipeline` z krokami `tfidf` i
`classifier` (tak zapisuje go skrypt z Colaba); działa też para
`(vectorizer, classifier)`. Klasyfikator musi rozpoznawać `[0, 1]`, gdzie
0 oznacza Normal, a 1 Anomaly. Wektoryzator ma być trenowany na tekście sesji
BlockID przygotowanym przez `scripts/prepare_hdfs_features.py`.

API składa cechy z surowych linii sesji w kolejności źródłowej. Linia jest
przypisana do pierwszego BlockID znalezionego w jej tekście, tak jak w kodzie
przygotowującym dane z Colaba.

Po pobraniu kodu przebuduj usługi przez `docker compose up --build api dashboard`.
Przy późniejszej wymianie samego artefaktu wystarczy `docker compose restart api`.
Endpoint `/health` pokaże `detection: configured`; nowe analizy
HDFS otrzymają wynik dla każdej grupy, której cechy są znane modelowi.
Przy uruchomieniu lokalnym bez Compose ustaw przed startem API
`DETECTION_MODEL_PATH` na ścieżkę do tego pliku, np. w PowerShell:
`$env:DETECTION_MODEL_PATH = "$PWD\models\baseline.joblib"`.
Z treningu zachowaj też `models/model_metadata.json`; zawiera schemat cech i
wersję scikit-learn używaną podczas treningu. API nie wymaga tego pliku.

Widok **Ocena modeli** korzysta z dołączonego pliku wyników w `reports/`:

```text
reports/training_metrics_20261117_123831.json
```

API automatycznie odczyta najnowszy `training_metrics_*.json` z `reports/`.
Plik wyników nie jest potrzebny do predykcji. Sam artefakt `baseline.joblib`
nie zawiera Precision/Recall/F1 ani etykiet testowych. Nie dodawaj dużych
zbiorów treningowych ani podziałów danych do repozytorium.

Wskazanie ML zachowuje identyfikator grupy oraz źródła rzeczywiście użyte do
obliczenia cech. Zdarzenie wymieniające kilka bloków jest oceniane dla pierwszego
BlockID; może nadal być widoczne jako kontekst pozostałych grup.
