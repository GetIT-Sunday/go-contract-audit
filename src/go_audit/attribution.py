"""Bounded one- and two-axis semantic attribution for reconstructable D."""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np

from .config import AuditConfig
from .ontology import Ontology, parse_obo
from .semantics import close_sets, filter_sets, namespace_view, threshold_sets

AXIS_TOKENS = (
    "prediction_closure", "truth_closure", "relation_set",
    "namespace_policy", "root_policy", "term_universe",
    "term_universe_label_dependence", "comparison_boundary",
    "threshold_representation", "alt_id_policy", "obsolete_policy",
)
SCIENTIFIC_AXIS = {axis: axis for axis in AXIS_TOKENS}
SCIENTIFIC_AXIS["term_universe_label_dependence"] = "term_universe"


def _close_within_namespace(predictions, ontology: Ontology):
    output = []
    for prediction in predictions:
        closed = set(prediction)
        for start in prediction:
            namespace = ontology.namespaces.get(ontology.canonical(start))
            stack = list(ontology.parents.get(ontology.canonical(start), ()))
            while stack:
                parent = stack.pop()
                if ontology.namespaces.get(parent) != namespace:
                    continue
                if parent not in closed:
                    closed.add(parent)
                    stack.extend(ontology.parents.get(parent, ()))
        output.append(closed)
    return output


def _reverse_aliases(ontology: Ontology) -> dict[str, str]:
    result = {}
    for alias, canonical in sorted(ontology.alt_ids.items()):
        result.setdefault(canonical, alias)
    return result


def canonicalize_sets(
    values: list[set[str]], ontology: Ontology, universe: set[str]
) -> list[set[str]]:
    """Apply the complete declared canonical map, including post-filtering."""
    return filter_sets(close_sets(values, ontology), universe)


def _object_distance(left: dict[str, Any], right: dict[str, Any]) -> int:
    difference = sum(
        len(a ^ b)
        for threshold in left["predictions"]
        for a, b in zip(left["predictions"][threshold], right["predictions"][threshold])
    )
    difference += sum(len(a ^ b) for a, b in zip(left["truth"], right["truth"]))
    return difference


def semantic_object(
    axes: frozenset[str], *, config: AuditConfig, ontology: Ontology,
    proteins: tuple[str, ...], terms: tuple[str, ...], scores: np.ndarray,
    raw_truth: list[set[str]], closed_truth: list[set[str]], canonical_universe: set[str],
) -> dict[str, Any]:
    relation_ontology = parse_obo(config.ontology.path, ("is_a",)) if "relation_set" in axes else ontology
    namespaces = set(config.ontology.namespace_roots)
    close_within = config.ontology.namespace_policy == "close_within_namespace"
    if "namespace_policy" in axes:
        close_within = not close_within
    graph_ontology = namespace_view(relation_ontology, namespaces) if close_within else relation_ontology
    universe = set(canonical_universe)
    if "term_universe" in axes:
        universe = set(terms)
    if "term_universe_label_dependence" in axes:
        universe = set().union(*closed_truth) if closed_truth else set()
    if "root_policy" in axes:
        universe |= set(config.ontology.namespace_roots.values())
    comparison = "greater" if "comparison_boundary" in axes else config.evaluation.comparison
    matrix = np.asarray(scores, float)
    if "threshold_representation" in axes:
        matrix = np.round(matrix, 2)
    predictions = {}
    for threshold in config.evaluation.threshold_grid.values:
        raw = threshold_sets(matrix, list(terms), threshold, comparison)
        if "prediction_closure" in axes:
            transformed = filter_sets(raw, universe)
        else:
            transformed = canonicalize_sets(raw, graph_ontology, universe)
        if "alt_id_policy" in axes:
            reverse = _reverse_aliases(ontology)
            transformed = [{reverse.get(term, term) for term in row} for row in transformed]
        if "obsolete_policy" in axes:
            inverse = {replacement: obsolete for obsolete, replacement in ontology.replacements.items()}
            transformed = [set(row) | {inverse[term] for term in row if term in inverse} for row in transformed]
        predictions[float(threshold)] = transformed
    # Candidate truth is always reconstructed forward from retained direct truth.
    # This is necessary for root inclusion and other candidate contracts that
    # cannot be inverted from an already filtered canonical truth object.
    truth = (
        filter_sets(raw_truth, universe)
        if "truth_closure" in axes
        else canonicalize_sets(raw_truth, graph_ontology, universe)
    )
    if "alt_id_policy" in axes:
        reverse = _reverse_aliases(ontology)
        truth = [{reverse.get(term, term) for term in row} for row in truth]
    if "obsolete_policy" in axes:
        inverse = {replacement: obsolete for obsolete, replacement in ontology.replacements.items()}
        truth = [set(row) | {inverse[term] for term in row if term in inverse} for row in truth]
    return {"predictions": predictions, "truth": truth}


def attribute_external(
    observed: dict[str, Any], *, config: AuditConfig, ontology: Ontology,
    proteins: tuple[str, ...], terms: tuple[str, ...], scores: np.ndarray,
    raw_truth: list[set[str]], closed_truth: list[set[str]], canonical_universe: set[str],
) -> dict[str, Any]:
    canonical = semantic_object(frozenset(), config=config, ontology=ontology, proteins=proteins, terms=terms, scores=scores, raw_truth=raw_truth, closed_truth=closed_truth, canonical_universe=canonical_universe)
    base_distance = _object_distance(observed, canonical)
    if base_distance == 0:
        return {"verdict": "CLOSED", "minimal_axis_sets": [], "rows": [], "distance": 0}
    candidates: dict[frozenset[str], tuple[dict[str, Any], int]] = {}
    rows = []
    reduced = []
    for axis in AXIS_TOKENS:
        axes = frozenset((axis,))
        candidate = semantic_object(axes, config=config, ontology=ontology, proteins=proteins, terms=terms, scores=scores, raw_truth=raw_truth, closed_truth=closed_truth, canonical_universe=canonical_universe)
        distance = _object_distance(observed, candidate)
        candidates[axes] = (candidate, distance)
        rows.append({"axis_set": axis, "difference_pairs": distance, "reconciles": distance == 0})
        if distance < base_distance:
            reduced.append(axis)
    exact = [axes for axes, (_, distance) in candidates.items() if distance == 0]
    if not exact:
        for left, right in combinations(reduced, 2):
            axes = frozenset((left, right))
            candidate = semantic_object(axes, config=config, ontology=ontology, proteins=proteins, terms=terms, scores=scores, raw_truth=raw_truth, closed_truth=closed_truth, canonical_universe=canonical_universe)
            distance = _object_distance(observed, candidate)
            rows.append({"axis_set": "+".join(sorted(axes)), "difference_pairs": distance, "reconciles": distance == 0})
            if distance == 0:
                exact.append(axes)
    minimum = min((len(axes) for axes in exact), default=None)
    minimal = sorted([sorted(axes) for axes in exact if len(axes) == minimum])
    verdict = "UNRESOLVED" if not minimal else ("ATTRIBUTED" if len(minimal) == 1 else "AMBIGUOUS")
    return {"verdict": verdict, "minimal_axis_sets": minimal, "rows": rows, "distance": base_distance}
