import json, datetime, os, sys
import pandas as pd, joblib
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix

P = "data/preprocessed/"
os.makedirs("models", exist_ok=True)
t = pd.read_csv(P + "Event_traces.csv").drop(columns=["Label"])
l = pd.read_csv(P + "anomaly_label.csv")
df = t.merge(l, on="BlockId")
df["y"] = (df["Label"] == "Anomaly").astype(int)
df["text"] = df["Features"].astype(str)

tr, tmp = train_test_split(df, test_size=0.3, stratify=df["y"], random_state=42)
val, te = train_test_split(tmp, test_size=0.5, stratify=tmp["y"], random_state=42)
for name, part in [("train", tr), ("val", val), ("test", te)]:
    part[["BlockId", "y"]].to_csv(f"models/split_{name}.csv", index=False)

vec = TfidfVectorizer(token_pattern=r"\d+")
clf = LogisticRegression(max_iter=1000, class_weight="balanced")
clf.fit(vec.fit_transform(tr["text"]), tr["y"])

def metrics(part):
    pred = clf.predict(vec.transform(part["text"]))
    p, r, f, _ = precision_recall_fscore_support(part["y"], pred, average="binary", zero_division=0)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "confusion_matrix": confusion_matrix(part["y"], pred, labels=[0, 1]).tolist(), "n": len(part)}

results = {"model": "tfidf-logreg-v1", "date": datetime.date.today().isoformat(),
           "dataset": os.getenv("DATASET_NAME", "Nie podano"),
           "data_source": os.getenv("DATA_SOURCE", "unknown"), "class_labels": [0, 1],
           "split": {"train": len(tr), "val": len(val), "test": len(te)},
           "validation": metrics(val)}
if "--test" in sys.argv:
    results["test"] = metrics(te)
joblib.dump((vec, clf), "models/baseline.joblib")
results_path = os.getenv("EVALUATION_RESULTS_PATH", "runtime/evaluation/results.json")
os.makedirs(os.path.dirname(os.path.abspath(results_path)), exist_ok=True)
with open(results_path, "w", encoding="utf-8") as results_file:
    json.dump(results, results_file, indent=2, ensure_ascii=False)
print(json.dumps(results, indent=2))
