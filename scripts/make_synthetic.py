import random
from pathlib import Path

import pandas as pd

random.seed(42)
N_NORMAL, N_ANOM = 6000, 200
NORMAL = ["E5","E22","E11","E9","E26","E3","E18","E25","E6","E16"]
ANOM = ["E7","E13","E14","E21","E28"]
rows, labels = [], []
for i in range(N_NORMAL + N_ANOM):
    anom = i >= N_NORMAL
    seq = [random.choice(NORMAL) for _ in range(random.randint(10, 40))]
    if anom:
        for _ in range(random.randint(2, 6)):
            seq.insert(random.randrange(len(seq)), random.choice(ANOM))
    bid = f"blk_{i}"
    rows.append({"BlockId": bid, "Label": "Success", "Type": 1, "Features": "[" + ",".join(seq) + "]"})
    labels.append({"BlockId": bid, "Label": "Anomaly" if anom else "Normal"})
output_dir = Path("data/preprocessed")
output_dir.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(output_dir / "Event_traces.csv", index=False)
pd.DataFrame(labels).to_csv(output_dir / "anomaly_label.csv", index=False)
print("OK: wygenerowano dane syntetyczne")
