"""Sprawdzenie zgodności predykcji z formatem artefaktu zapisywanego przez HD."""

import importlib.util
from pathlib import Path

import joblib
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


spec = importlib.util.spec_from_file_location(
    "hd_predict", Path(__file__).resolve().parents[1] / "scripts/predict.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def trained_baseline(tmp_path):
    features = ["[E1,E2]", "[E1,E1]", "[E2,E1]", "[E7,E9]", "[E9,E7]", "[E9,E9]"]
    vectorizer = TfidfVectorizer(token_pattern=r"\d+")
    classifier = LogisticRegression(class_weight="balanced", random_state=42)
    classifier.fit(vectorizer.fit_transform(features), [0, 0, 0, 1, 1, 1])
    path = tmp_path / "baseline.joblib"
    joblib.dump((vectorizer, classifier), path)
    return path


def test_saved_model_predicts_both_classes(trained_baseline):
    normal = module.predict("[E1,E2]", trained_baseline)
    anomaly = module.predict("[E7,E9]", trained_baseline)
    assert normal["is_anomaly"] is False and anomaly["is_anomaly"] is True
    assert normal["score"] < 0.5 < anomaly["score"]
    assert anomaly["score_type"] == "anomaly_probability"


@pytest.mark.parametrize("features", ["", " ", None, ["E1"]])
def test_invalid_features_are_rejected(trained_baseline, features):
    with pytest.raises(ValueError, match="Features"):
        module.predict(features, trained_baseline)


def test_unknown_features_are_not_silently_classified_as_normal(trained_baseline):
    with pytest.raises(ValueError, match="słownika"):
        module.predict("[E999,E888]", trained_baseline)
