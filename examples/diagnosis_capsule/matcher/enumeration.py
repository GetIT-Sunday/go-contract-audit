"""Exact candidate enumeration with no domain-specific candidate formulas."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .signature import ObservedSignature, signature_from_channels


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    components: frozenset[str]
    channels: Mapping[str, Any]


@dataclass(frozen=True)
class EquivalenceClass:
    signature_digest: str
    candidate_ids: tuple[str, ...]
    component_sets: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class EnumerationResult:
    observed: ObservedSignature
    candidates_evaluated: int
    exact_candidate_ids: tuple[str, ...]
    minimal_component_sets: tuple[tuple[str, ...], ...]
    equivalence_classes: tuple[EquivalenceClass, ...]

    @property
    def resolved(self) -> bool:
        return bool(self.minimal_component_sets)

    @property
    def ambiguous(self) -> bool:
        return len(self.minimal_component_sets) > 1


def _proper_subset_exists(components: frozenset[str], sets: Iterable[frozenset[str]]) -> bool:
    return any(other < components for other in sets)


def enumerate_explanations(observed_channels: Mapping[str, Any], candidates: Iterable[Candidate]) -> EnumerationResult:
    """Compare supplied candidate outputs and retain set-minimal exact explanations.

    Candidate construction is deliberately outside this module. A future frozen
    protocol must define which candidates are admissible and how they are built.
    """
    observed = signature_from_channels(observed_channels)
    materialized = sorted(candidates, key=lambda item: item.candidate_id)
    if len({item.candidate_id for item in materialized}) != len(materialized):
        raise ValueError("candidate_id values must be unique")
    signatures = {item.candidate_id: signature_from_channels(item.channels) for item in materialized}
    exact = [item for item in materialized if signatures[item.candidate_id].digest == observed.digest]
    exact_sets = {item.components for item in exact}
    minimal_sets = sorted((components for components in exact_sets if not _proper_subset_exists(components, exact_sets)), key=lambda values: (len(values), tuple(sorted(values))))
    grouped: dict[str, list[Candidate]] = {}
    for item in materialized:
        grouped.setdefault(signatures[item.candidate_id].digest, []).append(item)
    classes = tuple(
        EquivalenceClass(
            signature_digest=digest,
            candidate_ids=tuple(item.candidate_id for item in sorted(items, key=lambda item: item.candidate_id)),
            component_sets=tuple(sorted((tuple(sorted(item.components)) for item in items), key=lambda values: (len(values), values))),
        )
        for digest, items in sorted(grouped.items())
    )
    return EnumerationResult(
        observed=observed,
        candidates_evaluated=len(materialized),
        exact_candidate_ids=tuple(item.candidate_id for item in exact),
        minimal_component_sets=tuple(tuple(sorted(values)) for values in minimal_sets),
        equivalence_classes=classes,
    )

