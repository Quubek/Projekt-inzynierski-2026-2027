"""Odczyt wyników HD; dashboard nie trenuje ani nie ocenia modeli ponownie."""

import json
import os
from pathlib import Path

from log_analyzer.contracts import EvaluationResults, ExperimentResult


def load_evaluation_results() -> EvaluationResults:
    default = Path(__file__).resolve().parents[2] / "runtime/evaluation/results.json"
    path = Path(os.getenv("EVALUATION_RESULTS_PATH", str(default)))
    if not path.exists():
        return EvaluationResults()
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Plik wyników przekracza 1 MB.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "experiments" in data:
        return EvaluationResults.model_validate(data)
    return EvaluationResults(experiments=[ExperimentResult.model_validate(data)])
