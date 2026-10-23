"""Minimal third-party adapter plugin example."""
from __future__ import annotations

import json

from go_audit.model_adapters import AdaptResult


class MyJSONAdapter:
    name = "my-json"
    version = "1"
    description = "Example predictions JSON: {protein: {GO: score}}."

    def adapt(self, request):
        payload = json.loads(request.input_path.read_text())
        output = request.output_dir / "scores.tsv"
        rows = 0; proteins = set(); terms = set()
        with output.open("x") as handle:
            handle.write("protein_id\tgo_id\tscore\n")
            for protein in sorted(payload):
                proteins.add(protein)
                for term, score in sorted(payload[protein].items()):
                    terms.add(term); rows += 1
                    handle.write(f"{protein}\t{term}\t{float(score)!r}\n")
        return AdaptResult(output, "probability", "pre_hierarchy", "user_json", rows, len(proteins), len(terms))


def register_adapters(registry):
    registry.register("my-json", MyJSONAdapter, origin=__file__)

