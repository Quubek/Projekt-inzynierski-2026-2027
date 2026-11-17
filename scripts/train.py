"""Trenuj pipeline TF-IDF + LogisticRegression zgodny z predyktorem API."""

import argparse
import json
import os
import platform
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

SEED = 42
MODEL_VERSION = "log-anomaly-tfidf-lr-v1"


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=root / "data/preprocessed")
    parser.add_argument("--model-out", type=Path, default=root / "models/baseline.joblib")
    parser.add_argument("--metrics-out", type=Path)
    parser.add_argument("--metadata-out", type=Path)
    return parser.parse_args()


def load_data(data_dir: Path) -> pd.DataFrame:
    traces_path = data_dir / "Event_traces.csv"
    labels_path = data_dir / "anomaly_label.csv"
    if not traces_path.is_file() or not labels_path.is_file():
        raise FileNotFoundError(
            f"Brakuje {traces_path} lub {labels_path}. Najpierw uruchom prepare_hdfs_features.py."
        )
    traces = pd.read_csv(traces_path)
    labels = pd.read_csv(labels_path)
    if not {"BlockId", "Features"}.issubset(traces.columns):
        raise ValueError("Event_traces.csv musi zawierać BlockId i Features.")
    if not {"BlockId", "Label"}.issubset(labels.columns):
        raise ValueError("anomaly_label.csv musi zawierać BlockId i Label.")
    if traces["BlockId"].duplicated().any() or labels["BlockId"].duplicated().any():
        raise ValueError("Każdy BlockId może wystąpić tylko raz w każdym pliku.")
    df = traces[["BlockId", "Features"]].merge(
        labels[["BlockId", "Label"]], on="BlockId", how="inner", validate="one_to_one"
    )
    if df.empty:
        raise ValueError("Nie dopasowano BlockId między cechami i etykietami.")
    if df["Features"].isna().any() or df["Features"].astype(str).str.strip().eq("").any():
        raise ValueError("Features zawiera puste sesje.")
    unknown = set(df["Label"].dropna()) - {"Normal", "Anomaly"}
    if unknown or df["Label"].isna().any():
        raise ValueError(f"Label może zawierać tylko Normal/Anomaly: {sorted(unknown)}")
    df["label"] = (df["Label"] == "Anomaly").astype(int)
    counts = df["label"].value_counts()
    if len(counts) != 2 or counts.min() < 2:
        raise ValueError("Każda klasa musi mieć co najmniej dwa przykłady.")
    df["text"] = df["Features"].astype(str)
    return df


def build_model() -> Pipeline:
    return Pipeline(steps=[
        ("tfidf", TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            lowercase=True,
            strip_accents="unicode",
            sublinear_tf=True,
        )),
        ("classifier", LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=SEED,
            solver="liblinear",
        )),
    ])


def main() -> None:
    args = parse_args()
    df = load_data(args.data_dir)
    x_train, x_test, y_train, y_test = train_test_split(
        df["text"], df["label"], test_size=0.2, random_state=SEED, stratify=df["label"]
    )
    model = build_model()
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]
    matrix = confusion_matrix(y_test, predictions, labels=[0, 1])
    source = os.getenv("DATA_SOURCE", "unknown")
    if source not in {"synthetic", "loghub", "unknown"}:
        raise ValueError("DATA_SOURCE musi mieć wartość synthetic, loghub albo unknown.")
    dataset = os.getenv("DATASET_NAME", "HDFS_v1" if source == "loghub" else "Nie podano")

    metrics = {
        "model": MODEL_VERSION,
        "date": datetime.now().date().isoformat(),
        "dataset": dataset,
        "data_source": source,
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "n_anomalies_train": int(y_train.sum()),
        "n_anomalies_test": int(y_test.sum()),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
        "f1": float(f1_score(y_test, predictions, zero_division=0)),
        "accuracy": float(accuracy_score(y_test, predictions)),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "average_precision": float(average_precision_score(y_test, probabilities)),
        "confusion_matrix": matrix.tolist(),
        "classification_report": classification_report(
            y_test, predictions, labels=[0, 1], target_names=["Normal", "Anomaly"],
            zero_division=0,
        ),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metrics_path = args.metrics_out or args.model_out.parent.parent / "reports" / f"training_metrics_{stamp}.json"
    metadata_path = args.metadata_out or args.model_out.parent / "model_metadata.json"
    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    df.loc[x_train.index, ["BlockId"]].to_csv(args.model_out.parent / "split_train.csv", index=False)
    df.loc[x_test.index, ["BlockId"]].to_csv(args.model_out.parent / "split_test.csv", index=False)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model_out)
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metadata = {
        "model": MODEL_VERSION,
        "feature_schema": "hdfs-block-session-raw-text-v1",
        "dataset": dataset,
        "data_source": source,
        "class_labels": {"0": "Normal", "1": "Anomaly"},
        "python_version": platform.python_version(),
        "scikit_learn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Model zapisany: {args.model_out}")
    print(f"Metryki zapisane: {metrics_path}")
    print(f"Metadane zapisane: {metadata_path}")


if __name__ == "__main__":
    main()
