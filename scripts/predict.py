"""Predykcja dla tekstu sesji BlockID lub tekstu zgodnego z modelem."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from log_analyzer.detection.model import predict_features


def predict(features: str, model_path: str | Path = "models/baseline.joblib") -> dict:
    return predict_features(features, model_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("features", help="tekst sesji BlockID zgodny z modelem")
    parser.add_argument("--model", type=Path, default=Path("models/baseline.joblib"))
    args = parser.parse_args()
    print(json.dumps(predict(args.features, args.model), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
