"""Reproduce bounded diagnosis on retained public candidate surfaces."""
import argparse
import json
from pathlib import Path

from matcher.enumeration import Candidate, enumerate_explanations

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("audit", "check"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    cases = json.loads((root / "examples.json").read_text())
    if args.mode == "audit":
        rows = []
        for case in cases:
            candidates = [Candidate(c["id"], frozenset(c["axes"]), c["channels"]) for c in case["candidates"]]
            result = enumerate_explanations(case["observed"], candidates)
            rows.append({"id": case["id"], "level": case["level"],
                "exact_ids": list(result.exact_candidate_ids),
                "minimal": [list(x) for x in result.minimal_component_sets],
                "partition": sorted(sorted(g.candidate_ids) for g in result.equivalence_classes)})
        with args.out.open("x") as f:
            json.dump(rows, f, indent=2, sort_keys=True)
        print("AUDIT", len(rows), "cases; expected labels not read")
    else:
        from reference import ReferenceIndex
        rows = json.loads(args.out.read_text())
        expected = json.loads((root / "expected.json").read_text())
        assert len(rows) == len(cases) == len(expected)
        for case, row in zip(cases, rows):
            ref = ReferenceIndex(case["candidates"]).match(case["observed"])
            assert row["id"] == case["id"]
            assert all(row[key] == ref[key] == expected[row["id"]][key]
                       for key in ("exact_ids", "minimal", "partition"))
        print("CHECK PASS", len(rows), "cases; independent reference and frozen expected sets agree")

if __name__ == "__main__":
    main()
