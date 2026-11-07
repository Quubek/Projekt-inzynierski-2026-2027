"""Demonstracja HTTP; najpierw uruchom API na 127.0.0.1:8000."""
import json
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
payload = json.loads((root / "data/samples/hdfs_request.json").read_text())
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15) as client:
    print("GET /health:", client.get("/health").status_code)
    response = client.post("/api/v1/analyze", json=payload)
    response.raise_for_status()
    result = response.json()
    print("POST /api/v1/analyze:", response.status_code)
    print("Liczba wpisow:", len(result["events"]))
    print("Liczba grup BlockID:", len(result["groups"]))
    for event in result["events"]:
        print("Szablon:", event["template"])
    print("Status detekcji:", result["detection_status"])
    bad = client.post("/api/v1/analyze", json={"logs": []})
    print("Pusta paczka:", bad.status_code, "(oczekiwane 422)")
    output = root / "runtime" / "demo-response.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Zapisano odpowiedz:", output)
