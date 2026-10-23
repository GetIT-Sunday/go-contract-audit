"""Independent JSON-domain matcher. Standard library only; no production imports.

Equality uses typed trees, not production signatures or cryptographic digests.
Minimal explanations are obtained by an ascending-cardinality antichain sweep.
"""
from __future__ import annotations

import math


def value_tree(value):
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite public value")
        return ("float", value.hex())
    if type(value) is str:
        return ("str", value)
    if isinstance(value, (tuple, list)):
        return ("sequence", tuple(value_tree(x) for x in value))
    if isinstance(value, dict):
        if not all(type(k) is str for k in value):
            raise ValueError("public object keys must be strings")
        return ("object", tuple((k, value_tree(value[k])) for k in sorted(value)))
    raise TypeError("outside public JSON domain: " + type(value).__name__)


def ordered_sets(values):
    return sorted((sorted(x) for x in set(map(frozenset, values))), key=lambda x: (len(x), x))


class ReferenceIndex:
    def __init__(self, candidates):
        self.candidates = sorted(candidates, key=lambda x: x["id"])
        ids = [c["id"] for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate_id")
        self.values = [value_tree(c["channels"]) for c in self.candidates]
        self.groups = []
        representatives = []
        for c, tree in zip(self.candidates, self.values):
            for i, rep in enumerate(representatives):
                if tree == rep:
                    self.groups[i].append(c["id"])
                    break
            else:
                representatives.append(tree)
                self.groups.append([c["id"]])

    def match(self, observed):
        if not observed:
            raise ValueError("empty observed channels")
        tree = value_tree(observed)
        exact = [c for c, v in zip(self.candidates, self.values) if tree == v]
        # Larger sets cannot dominate earlier, smaller accepted sets.
        accepted = []
        for axes in ordered_sets(c["axes"] for c in exact):
            if not any(set(previous).issubset(axes) for previous in accepted):
                accepted.append(axes)
        return {"exact_ids": [c["id"] for c in exact], "minimal": accepted,
                "partition": sorted(sorted(g) for g in self.groups)}


def public_state(minimal, level, suite):
    if not minimal:
        return "UNRESOLVED"
    if minimal == [[]]:
        return "EQUIVALENT" if suite == "B" else "NO_EFFECT"
    if len(minimal) > 1:
        return "EQUIVALENCE_CLASS"
    if level in {"AGGREGATE_ONLY", "FMAX_ONLY"}:
        return "EQUIVALENCE_CLASS" if suite == "B" else "UNSUPPORTED_SPECIFICITY"
    return "UNIQUE_ATTRIBUTION"
