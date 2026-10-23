"""Adapter execution, canonical conformance checks, and provenance outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .base import AdaptRequest, ModelAdapterError
from .registry import AdapterRegistry


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""): digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    if path.exists(): raise FileExistsError(path)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _validate_long_tsv(path: Path) -> dict[str, Any]:
    rows = 0; proteins = set(); terms = set(); finite = bounded = True; empty_ids = 0
    digest = hashlib.sha256()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["protein_id", "go_id", "score"]:
            raise ModelAdapterError("canonical output header must be protein_id, go_id, score")
        for row in reader:
            protein, term = row["protein_id"].strip(), row["go_id"].strip()
            try: score = float(row["score"])
            except ValueError as exc: raise ModelAdapterError(f"invalid canonical score at row {rows + 2}") from exc
            rows += 1; proteins.add(protein); terms.add(term); empty_ids += int(not protein or not term)
            finite &= math.isfinite(score); bounded &= 0.0 <= score <= 1.0
            digest.update(f"{protein}\t{term}\t{score.hex()}\n".encode())
    passed = rows > 0 and not empty_ids and finite and bounded
    return {
        "schema": "goaudit.adapter-conformance.v1", "status": "PASS" if passed else "FAIL",
        "rows": rows, "proteins": len(proteins), "terms": len(terms), "empty_identifiers": empty_ids,
        "scores_finite": finite, "scores_in_unit_interval": bounded, "canonical_value_sha256": digest.hexdigest(),
        "duplicate_policy": "validated by the downstream audit contract",
        "truth_provided_to_adapter": False, "metric_api_provided_to_adapter": False,
    }


def _decode(values) -> list[str]:
    return [x.decode() if isinstance(x, bytes) else str(x) for x in values]


def _validate_hdf5(path: Path) -> dict[str, Any]:
    try:
        import h5py
        import numpy as np
    except ImportError as exc:
        raise ModelAdapterError("canonical HDF5 validation requires h5py and numpy") from exc
    finite = bounded = True; digest = hashlib.sha256()
    with h5py.File(path, "r") as handle:
        missing = {"protein_ids", "term_ids", "scores"} - set(handle)
        if missing: raise ModelAdapterError(f"canonical HDF5 datasets missing: {sorted(missing)}")
        proteins, terms = _decode(handle["protein_ids"][:]), _decode(handle["term_ids"][:]); scores = handle["scores"]
        if scores.shape != (len(proteins), len(terms)): raise ModelAdapterError("canonical HDF5 matrix shape mismatch")
        if len(proteins) != len(set(proteins)) or len(terms) != len(set(terms)): raise ModelAdapterError("canonical HDF5 axes are not unique")
        for start in range(0, len(proteins), 32):
            block = np.asarray(scores[start:start + 32], dtype=np.float32)
            finite &= bool(np.isfinite(block).all()); bounded &= bool(np.all((block >= 0) & (block <= 1)))
            for local, protein in enumerate(proteins[start:start + len(block)]):
                for term, score in zip(terms, block[local]): digest.update(f"{protein}\t{term}\t{float(score).hex()}\n".encode())
        schema = str(handle.attrs.get("schema_version", ""))
    passed = bool(proteins and terms and finite and bounded and schema == "goaudit.canonical-scores.v1")
    return {"schema": "goaudit.adapter-conformance.v1", "status": "PASS" if passed else "FAIL", "rows": len(proteins) * len(terms), "proteins": len(proteins), "terms": len(terms), "empty_identifiers": sum(not x for x in proteins + terms), "scores_finite": finite, "scores_in_unit_interval": bounded, "canonical_value_sha256": digest.hexdigest(), "duplicate_policy": "dense axes unique", "truth_provided_to_adapter": False, "metric_api_provided_to_adapter": False}


def validate_canonical(path: Path, canonical_format: str = "long_tsv") -> dict[str, Any]:
    if canonical_format == "long_tsv": return _validate_long_tsv(path)
    if canonical_format == "hdf5_matrix": return _validate_hdf5(path)
    raise ModelAdapterError(f"unsupported canonical format {canonical_format}")


def run_adapter(registry: AdapterRegistry, name: str, input_path: Path, output_dir: Path, options: Mapping[str, Any], plugin_origins: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    input_path, output_dir = input_path.resolve(), output_dir.resolve()
    if not input_path.is_file(): raise FileNotFoundError(input_path)
    if output_dir.exists(): raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True)
    adapter = registry.create(name); source_hash = _sha(input_path)
    result = adapter.adapt(AdaptRequest(input_path, output_dir, dict(options)))
    canonical = result.canonical_path.resolve()
    if canonical.parent != output_dir or not canonical.is_file():
        raise ModelAdapterError("adapter canonical output must be a file directly inside output_dir")
    conformance = validate_canonical(canonical, result.canonical_format)
    if conformance["status"] != "PASS":
        raise ModelAdapterError("canonical output failed conformance; see conformance values in the source adapter test")
    declared = {"rows": result.declared_rows, "proteins": result.declared_proteins, "terms": result.declared_terms}
    for key, value in declared.items():
        if value is not None and int(value) != int(conformance[key]): raise ModelAdapterError(f"adapter declared {key} does not match canonical output")
    manifest = {
        "schema": "goaudit.model-adapter-run.v1", "adapter": {"name": adapter.name, "version": str(adapter.version), "description": str(adapter.description)},
        "source": {"path": str(input_path), "bytes": input_path.stat().st_size, "sha256": source_hash, "format": result.source_format},
        "canonical": {"path": canonical.name, "format": result.canonical_format, "bytes": canonical.stat().st_size, "sha256": _sha(canonical), "score_semantics": result.score_semantics, "output_stage": result.output_stage},
        "conversion_events": list(result.conversion_events), "options": dict(sorted(options.items())), "plugins": list(plugin_origins or []),
        "truth_provided_to_adapter": False, "metric_api_provided_to_adapter": False,
        "threshold_selection_api_provided_to_adapter": False,
    }
    _write_json(output_dir / "conformance.json", conformance); _write_json(output_dir / "adapter_manifest.json", manifest)
    return {"manifest": manifest, "conformance": conformance}
