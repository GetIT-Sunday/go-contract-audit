"""Canonical A/B/C semantic equivalence operations."""
from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np

from .ontology import Ontology


def namespace_view(ontology: Ontology, namespaces: set[str]) -> Ontology:
    """Return an upward graph whose traversed edges remain in namespace."""
    parents = {}
    for term, term_parents in ontology.parents.items():
        namespace = ontology.namespaces.get(term)
        parents[term] = frozenset(
            parent for parent in term_parents
            if namespace in namespaces and ontology.namespaces.get(parent) == namespace
        )
    return Ontology(
        parents=parents,
        namespaces=dict(ontology.namespaces),
        obsolete=ontology.obsolete,
        alt_ids=dict(ontology.alt_ids),
        relation_counts=dict(ontology.relation_counts),
        replacements=dict(ontology.replacements),
        considers=dict(ontology.considers),
    )


def threshold_sets(scores: np.ndarray, terms: list[str], threshold: float, boundary: str) -> list[set[str]]:
    matrix = np.asarray(scores)
    if matrix.ndim != 2 or matrix.shape[1] != len(terms):
        raise ValueError("score/term shape mismatch")
    mask = matrix >= threshold if boundary == "greater_equal" else matrix > threshold
    term_array = np.asarray(terms)
    return [set(term_array[row].tolist()) for row in mask]


def close_sets(predictions: Iterable[set[str]], ontology: Ontology) -> list[set[str]]:
    output: list[set[str]] = []
    for prediction in predictions:
        closed = set(prediction)
        for term in prediction:
            closed.update(ontology.ancestors(term))
        output.append(closed)
    return output


def filter_sets(predictions: Iterable[set[str]], universe: set[str]) -> list[set[str]]:
    return [set(prediction) & universe for prediction in predictions]


def ancestor_max(scores: np.ndarray, source_terms: list[str], output_terms: list[str], ontology: Ontology) -> np.ndarray:
    matrix = np.asarray(scores, dtype=np.float64)
    output = np.zeros((len(matrix), len(output_terms)), dtype=np.float64)
    for column, ancestor in enumerate(output_terms):
        descendants = [index for index, term in enumerate(source_terms) if term == ancestor or ancestor in ontology.ancestors(term)]
        if descendants:
            output[:, column] = matrix[:, descendants].max(axis=1)
    return output


def pair_digest(proteins: list[str], predictions: Iterable[set[str]]) -> str:
    digest = hashlib.sha256()
    for protein, terms in sorted(zip(proteins, predictions)):
        for term in sorted(terms):
            digest.update(f"{protein}\t{term}\n".encode())
    return digest.hexdigest()


def symmetric_differences(proteins: list[str], reference: list[set[str]], candidate: list[set[str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for protein, left, right in zip(proteins, reference, candidate):
        rows.extend({"protein_id": protein, "go_id": term, "difference": "missing_from_candidate"} for term in sorted(left - right))
        rows.extend({"protein_id": protein, "go_id": term, "difference": "extra_in_candidate"} for term in sorted(right - left))
    return rows
