"""Public model-output adapter contract.

Adapters only translate prediction outputs into the canonical long TSV. They do
not receive truth labels, select thresholds, run metrics, or choose remediation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


class ModelAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdaptRequest:
    input_path: Path
    output_dir: Path
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdaptResult:
    canonical_path: Path
    score_semantics: str
    output_stage: str
    source_format: str
    declared_rows: int | None = None
    declared_proteins: int | None = None
    declared_terms: int | None = None
    conversion_events: tuple[Mapping[str, Any], ...] = ()
    canonical_format: str = "long_tsv"


class ModelOutputAdapter(Protocol):
    name: str
    version: str
    description: str

    def adapt(self, request: AdaptRequest) -> AdaptResult:
        ...


def option(options: Mapping[str, Any], name: str, default: Any = None) -> Any:
    value = options.get(name, default)
    if isinstance(value, str) and value == "":
        raise ModelAdapterError(f"adapter option {name} cannot be empty")
    return value
