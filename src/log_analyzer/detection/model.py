"""Adapter cech HDFS i predykcja TF-IDF dla grup BlockID."""

from functools import lru_cache
from pathlib import Path

import joblib

MODEL_VERSION = "log-anomaly-tfidf-lr-v1"


def features_from_events(events) -> str:
    """Łączy surowe linie sesji tak samo jak przygotowanie danych Colaba."""
    return " ".join(event.raw for event in events)


def features_from_block(block_id: str, events) -> str:
    """Odtwarza BlockSession.text: linia należy do pierwszego BlockID w logu."""
    return features_from_events([
        event for event in events
        if event.block_ids and event.block_ids[0] == block_id
    ])


@lru_cache(maxsize=4)
def _load_model(path: str, modified_ns: int):
    model = joblib.load(path)
    if isinstance(model, tuple) and len(model) == 2:
        vectorizer, classifier = model
    elif hasattr(model, "named_steps") and hasattr(model, "predict_proba"):
        vectorizer = model.named_steps.get("tfidf")
        classifier = model
        if vectorizer is None:
            raise ValueError("Pipeline musi zawierać krok TF-IDF o nazwie 'tfidf'.")
    else:
        raise ValueError("Nieobsługiwany artefakt. Oczekuję Pipeline TF-IDF albo pary (vectorizer, classifier).")
    if list(classifier.classes_) != [0, 1]:
        raise ValueError("Model musi rozpoznawać klasy 0 (normalne) i 1 (anomalia).")
    return model, vectorizer, classifier


def model_is_available(model_path: str | Path = "models/baseline.joblib") -> bool:
    return Path(model_path).is_file()


def predict_features(features: str, model_path: str | Path = "models/baseline.joblib") -> dict:
    """Klasyfikuje tekst cech; odrzuca wejście bez znanych tokenów modelu."""
    if not isinstance(features, str) or not features.strip():
        raise ValueError("Predykcja wymaga niepustego tekstu Features.")
    path = Path(model_path).resolve()
    model, vectorizer, classifier = _load_model(str(path), path.stat().st_mtime_ns)
    vectors = vectorizer.transform([features])
    if vectors.nnz == 0:
        raise ValueError("Żadna cecha nie należy do słownika wytrenowanego modelu.")
    if hasattr(model, "named_steps"):
        prediction = int(model.predict([features])[0])
        probabilities = model.predict_proba([features])[0]
    else:
        prediction = int(classifier.predict(vectors)[0])
        probabilities = classifier.predict_proba(vectors)[0]
    return {
        "is_anomaly": prediction == 1,
        "score": float(probabilities[list(classifier.classes_).index(1)]),
        "score_type": "anomaly_probability",
        "model_version": MODEL_VERSION,
    }
