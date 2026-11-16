import json, os, sys, pandas as pd
from predict import predict

P = "data/preprocessed/"
df = pd.read_csv(P + "Event_traces.csv").drop(columns=["Label"]).merge(
     pd.read_csv(P + "anomaly_label.csv"), on="BlockId")
val_ids = set(pd.read_csv("models/split_val.csv")["BlockId"])
df = df[df["BlockId"].isin(val_ids)]

ok = True
for lab, expected in [("Normal", False), ("Anomaly", True)]:
    sample = df[df["Label"] == lab]["Features"].head(20)
    hits = sum(predict(f)["is_anomaly"] == expected for f in sample)
    print(f"{lab}: {hits}/{len(sample)} zgodnych z oczekiwaniem")
    ok &= hits / max(len(sample), 1) >= 0.8

results_path = os.getenv("EVALUATION_RESULTS_PATH", "runtime/evaluation/results.json")
with open(results_path, encoding="utf-8") as results_file:
    res = json.load(results_file)
for k in ("precision", "recall", "f1"):
    assert k in res["validation"], f"brak {k} w {results_path}"
print("Walidacja:", res["validation"])
print("TEST ZALICZONY" if ok else "TEST NIEZALICZONY")
sys.exit(0 if ok else 1)
