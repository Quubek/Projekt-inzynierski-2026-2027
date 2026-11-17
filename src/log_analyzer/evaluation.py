"""Odczyt wyników HD; dashboard nie trenuje ani nie ocenia modeli ponownie."""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from log_analyzer.contracts import (
    DetectionMetrics,
    EvaluationResults,
    ExperimentResult,
    ExperimentSplit,
)


def _colab_result(data: dict, path: Path) -> ExperimentResult:
    """Mapuje płaski JSON treningu z Colaba do kontraktu dashboardu."""
    matrix = data.get("confusion_matrix")
    if not isinstance(matrix, list) or len(matrix) != 2 or any(len(row) != 2 for row in matrix):
        raise ValueError("Metryki Colaba wymagają macierzy pomyłek 2 × 2.")
    tn, fp = matrix[0]
    fn, tp = matrix[1]
    n_test = int(data.get("n_test", sum(sum(row) for row in matrix)))
    if sum(sum(row) for row in matrix) != n_test:
        raise ValueError("Macierz pomyłek nie zgadza się z n_test.")

    def ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    def class_metrics(tp_value: int, fp_value: int, fn_value: int, support: int) -> dict[str, float]:
        precision = ratio(tp_value, tp_value + fp_value)
        recall = ratio(tp_value, tp_value + fn_value)
        f1 = ratio(2 * precision * recall, precision + recall)
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1-score": round(f1, 4),
            "support": float(support),
        }

    metrics = DetectionMetrics(
        precision=float(data["precision"]),
        recall=float(data["recall"]),
        f1=float(data["f1"]),
        accuracy=ratio(tn + tp, n_test),
        roc_auc=float(data["roc_auc"]) if data.get("roc_auc") is not None else None,
        average_precision=(
            float(data["average_precision"])
            if data.get("average_precision") is not None else None
        ),
        per_class={
            "Normal": class_metrics(tn, fn, fp, tn + fp),
            "Anomaly": class_metrics(tp, fp, fn, fn + tp),
        },
        confusion_matrix=matrix,
        n=n_test,
    )

    match = re.search(r"training_metrics_(\d{8})_", path.name)
    result_date = (
        datetime.strptime(match.group(1), "%Y%m%d").date()
        if match else date.fromtimestamp(path.stat().st_mtime)
    )
    return ExperimentResult(
        model=data.get("model", "tfidf-logistic-regression"),
        date=result_date,
        dataset=data.get("dataset", "HDFS_v1"),
        data_source=data.get("data_source", "loghub"),
        class_labels=[0, 1],
        split=ExperimentSplit(
            train=int(data["n_train"]),
            val=0,
            test=n_test,
        ),
        test=metrics,
    )


def _read_result(path: Path) -> EvaluationResults:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Plik wyników przekracza 1 MB.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "experiments" in data:
        return EvaluationResults.model_validate(data)
    if isinstance(data, dict) and {"n_train", "n_test", "confusion_matrix"}.issubset(data):
        return EvaluationResults(experiments=[_colab_result(data, path)])
    return EvaluationResults(experiments=[ExperimentResult.model_validate(data)])


def load_evaluation_results() -> EvaluationResults:
    project_root = Path(__file__).resolve().parents[2]
    if configured_path := os.getenv("EVALUATION_RESULTS_PATH"):
        path = Path(configured_path)
        return _read_result(path) if path.exists() else EvaluationResults()

    reports = sorted((project_root / "reports").glob("training_metrics_*.json"))
    if reports:
        return _read_result(reports[-1])

    standard = project_root / "runtime/evaluation/results.json"
    return _read_result(standard) if standard.exists() else EvaluationResults()
