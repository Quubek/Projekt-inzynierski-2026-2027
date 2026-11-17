"""Przygotuj sesje tekstowe BlockID zgodne z modelem trenowanym w Colabie."""

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from tqdm import tqdm


LOG_PATTERN = re.compile(
    r"^(?P<date>\d{6}\s+\d{6})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<component>[\w\.]+):\s+"
    r"(?P<message>.*)$"
)
BLOCK_PATTERN = re.compile(r"blk_-?\d+")
LABEL_COLUMNS = {"label", "anomaly", "class", "ground_truth"}
BLOCK_COLUMNS = {"blockid", "block_id", "block"}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=root / "data/raw/HDFS.log")
    parser.add_argument("--labels", type=Path, default=root / "data/raw/anomaly_label.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "data/preprocessed")
    return parser.parse_args()


def _label(value) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"anomaly", "anomalies", "1", "true"}:
        return "Anomaly"
    if normalized in {"normal", "0", "false"}:
        return "Normal"
    raise ValueError(f"Nieznana etykieta: {value}")


def prepare(log_path: Path, labels_path: Path, output_dir: Path) -> int:
    labels = pd.read_csv(labels_path)
    block_column = next(
        (column for column in labels.columns if str(column).strip().lower() in BLOCK_COLUMNS), None
    )
    label_column = next(
        (column for column in labels.columns if str(column).strip().lower() in LABEL_COLUMNS), None
    )
    if block_column is None or label_column is None:
        raise ValueError("CSV etykiet musi mieć kolumnę BlockId i kolumnę Label/Anomaly/Class.")

    labels = labels[[block_column, label_column]].copy()
    labels.columns = ["BlockId", "Label"]
    labels["BlockId"] = labels["BlockId"].astype(str)
    labels["Label"] = labels["Label"].map(_label)
    if labels["BlockId"].duplicated().any():
        labels = labels.drop_duplicates("BlockId", keep="first")
    label_by_id = dict(zip(labels["BlockId"], labels["Label"]))

    messages_by_block: dict[str, list[str]] = defaultdict(list)
    with log_path.open("r", encoding="utf-8", errors="ignore") as source:
        for raw_line in tqdm(source, desc="Parsowanie HDFS"):
            raw = raw_line.rstrip("\r\n")
            if not raw:
                continue
            match = LOG_PATTERN.match(raw)
            message = match.group("message") if match else raw
            block_match = BLOCK_PATTERN.search(message)
            if block_match:
                # Zachowujemy zachowanie treningowego parsera Colaba: linia
                # należy do pierwszego BlockID w jej treści.
                messages_by_block[block_match.group(0)].append(message)

    rows = [
        {"BlockId": block_id, "Features": " ".join(messages)}
        for block_id, messages in messages_by_block.items()
        if block_id in label_by_id
    ]
    if not rows:
        raise ValueError("Nie dopasowano BlockID z logów do pliku etykiet.")

    traces = pd.DataFrame(rows)
    output_labels = traces[["BlockId"]].copy()
    output_labels["Label"] = output_labels["BlockId"].map(label_by_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    traces.to_csv(output_dir / "Event_traces.csv", index=False)
    output_labels.to_csv(output_dir / "anomaly_label.csv", index=False)
    print(f"Przygotowano {len(traces)} sesji BlockID w {output_dir}")
    return len(traces)


def main() -> None:
    args = parse_args()
    prepare(args.log, args.labels, args.output_dir)


if __name__ == "__main__":
    main()
