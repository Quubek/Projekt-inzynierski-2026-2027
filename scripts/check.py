import json, sys, pandas as pd
from predict import predict

P = "data/preprocessed/"
df = pd.read_csv(P + "Event_traces.csv").drop(columns=["Label"]).merge(
     pd.read_csv(P + "anomaly_label.csv"), on="BlockId")
te_ids = set(pd.read_csv("models/split_test.csv")["BlockId"])
df = df[df["BlockId"].isin(te_ids)]

ok = True
for lab, expected in [("Normal", False), ("Anomaly", True)]:
    sample = df[df["Label"] == lab]["Features"].head(20)
    hits = sum(predict(f)["is_anomaly"] == expected for f in sample)
    print(f"{lab}: {hits}/{len(sample)} zgodnych z oczekiwaniem")
    ok &= hits / max(len(sample), 1) >= 0.8

res = json.load(open("results.json"))
for k in ("precision", "recall", "f1"):
    assert k in res["validation"], f"brak {k} w results.json"
print("results.json:", res["validation"])
print("TEST ZALICZONY" if ok else "TEST NIEZALICZONY")
sys.exit(0 if ok else 1)
