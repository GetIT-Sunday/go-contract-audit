"""Public observed-evaluator adapter used by controlled fixtures."""
from __future__ import annotations
import json
from pathlib import Path

def load_observed(*, proteins, terms, scores, thresholds, contract, options):
    path = Path(options["observed_path"])
    value = json.loads(path.read_text())
    if value["proteins"] != proteins:
        raise ValueError("observed evaluator protein order mismatch")
    predictions = {
        float(threshold): [set(row) for row in rows]
        for threshold, rows in value["predictions"].items()
    }
    return {"predictions": predictions, "truth": [set(row) for row in value["truth"]]}
