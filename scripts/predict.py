"""Predykcja baseline'u HD dla gotowej kolumny Features, nie surowych logów."""

from functools import lru_cache
from pathlib import Path

import joblib


@lru_cache(maxsize=2)
def _load_model(path: str, modified_ns: int):
    # Czas modyfikacji unieważnia cache po ponownym treningu w tym samym procesie.
    vectorizer, classifier = joblib.load(path)
    if list(classifier.classes_) != [0, 1]:
        raise ValueError("Model musi rozpoznawać klasy 0 (normalne) i 1 (anomalia).")
    return vectorizer, classifier


def predict(features: str, model_path: str | Path = "models/baseline.joblib") -> dict:
    """Oczekuje dokładnie tej reprezentacji Features, na której uczono model."""
    if not isinstance(features, str) or not features.strip():
        raise ValueError("Predykcja wymaga niepustego tekstu z kolumny Features.")
    path = Path(model_path).resolve()
    vectorizer, classifier = _load_model(str(path), path.stat().st_mtime_ns)
    vectors = vectorizer.transform([features])
    if vectors.nnz == 0:
        raise ValueError("Żadna cecha nie należy do słownika wytrenowanego modelu.")
    return {
        "is_anomaly": bool(classifier.predict(vectors)[0] == 1),
        "score": float(classifier.predict_proba(vectors)[0, 1]),
        "score_type": "anomaly_probability",
        "model_version": "tfidf-logreg-v1",
    }
