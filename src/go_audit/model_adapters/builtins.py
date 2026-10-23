"""Built-in adapters for common GO-prediction output formats."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .base import AdaptRequest, AdaptResult, ModelAdapterError, option


def _output(request: AdaptRequest) -> Path:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    path = request.output_dir / "scores.tsv"
    if path.exists():
        raise FileExistsError(path)
    return path


def _matrix_output(request: AdaptRequest) -> Path:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    path = request.output_dir / "scores.h5"
    if path.exists(): raise FileExistsError(path)
    return path


def _requested_format(request: AdaptRequest, *, matrix_default: bool) -> str:
    value = str(option(request.options, "canonical_format", "hdf5_matrix" if matrix_default else "long_tsv"))
    if value not in {"long_tsv", "hdf5_matrix"}:
        raise ModelAdapterError("canonical_format must be long_tsv or hdf5_matrix")
    return value


def _write_matrix(path: Path, proteins, terms, scores, *, score_semantics: str, output_stage: str, chunk_rows: int = 32) -> None:
    try:
        import h5py
    except ImportError as exc:
        raise ModelAdapterError("canonical HDF5 output requires h5py") from exc
    string_type = h5py.string_dtype(encoding="utf-8")
    shape = (len(proteins), len(terms))
    with h5py.File(path, "x") as target:
        target.attrs["schema_version"] = "goaudit.canonical-scores.v1"
        target.attrs["score_semantics"] = score_semantics
        target.attrs["output_stage"] = output_stage
        target.create_dataset("protein_ids", data=np.asarray(proteins, dtype=object), dtype=string_type)
        target.create_dataset("term_ids", data=np.asarray(terms, dtype=object), dtype=string_type)
        dataset = target.create_dataset("scores", shape=shape, dtype="f4", chunks=(min(chunk_rows, max(1, shape[0])), min(2048, max(1, shape[1]))), compression="gzip", compression_opts=4, shuffle=True)
        for start in range(0, shape[0], chunk_rows):
            dataset[start:start + chunk_rows] = np.asarray(scores[start:start + chunk_rows], dtype=np.float32)


def _write_rows(path: Path, rows: Iterable[tuple[str, str, float]]) -> int:
    count = 0
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("protein_id", "go_id", "score"))
        for protein, term, score in rows:
            writer.writerow((protein, term, repr(float(score)))); count += 1
    return count


class CanonicalTSVAdapter:
    name = "canonical-tsv"
    version = "1"
    description = "Headered protein/GO/continuous-score table; field names are configurable."

    def adapt(self, request: AdaptRequest) -> AdaptResult:
        delimiter = str(option(request.options, "delimiter", "\t"))
        protein_field = str(option(request.options, "protein_field", "protein_id"))
        term_field = str(option(request.options, "term_field", "go_id"))
        score_field = str(option(request.options, "score_field", "score"))
        def rows():
            with request.input_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                required = {protein_field, term_field, score_field}
                if not required <= set(reader.fieldnames or ()):
                    raise ModelAdapterError(f"input requires fields {sorted(required)}")
                for row in reader:
                    yield row[protein_field].strip(), row[term_field].strip(), float(row[score_field])
        canonical_format = _requested_format(request, matrix_default=False)
        if canonical_format != "long_tsv": raise ModelAdapterError("canonical-tsv currently outputs long_tsv; use hdf5-matrix for dense HDF5")
        path = _output(request); count = _write_rows(path, rows())
        return AdaptResult(path, str(option(request.options, "score_semantics", "probability")), str(option(request.options, "output_stage", "unspecified")), "headered_delimited_text", declared_rows=count, canonical_format=canonical_format)


class HDF5MatrixAdapter:
    version = "1"
    description = "HDF5 matrix with protein_ids, term_ids, and scores datasets."

    def __init__(self, name: str = "hdf5-matrix"):
        self.name = name

    def adapt(self, request: AdaptRequest) -> AdaptResult:
        try:
            import h5py
        except ImportError as exc:
            raise ModelAdapterError("hdf5 adapters require h5py") from exc
        protein_key = str(option(request.options, "protein_dataset", "protein_ids"))
        term_key = str(option(request.options, "term_dataset", "term_ids"))
        score_key = str(option(request.options, "score_dataset", "scores"))
        transform = str(option(request.options, "transform", "identity"))
        chunk_rows = int(option(request.options, "chunk_rows", 32))
        if transform not in {"identity", "sigmoid"} or chunk_rows < 1:
            raise ModelAdapterError("transform must be identity/sigmoid and chunk_rows must be positive")
        canonical_format = _requested_format(request, matrix_default=True)
        score_semantics = "probability" if transform == "sigmoid" else str(option(request.options, "score_semantics", "probability"))
        output_stage = str(option(request.options, "output_stage", "pre_hierarchy"))
        path = _matrix_output(request) if canonical_format == "hdf5_matrix" else _output(request)
        with h5py.File(request.input_path, "r") as source:
            missing = {protein_key, term_key, score_key} - set(source)
            if missing: raise ModelAdapterError(f"HDF5 datasets missing: {sorted(missing)}")
            proteins = [x.decode() if isinstance(x, bytes) else str(x) for x in source[protein_key][:]]
            terms = [x.decode() if isinstance(x, bytes) else str(x) for x in source[term_key][:]]
            scores = source[score_key]
            if scores.shape != (len(proteins), len(terms)):
                raise ModelAdapterError("score matrix shape does not match axes")
            if len(set(proteins)) != len(proteins) or len(set(terms)) != len(terms):
                raise ModelAdapterError("HDF5 protein and term axes must be unique")
            def blocks():
                for start in range(0, len(proteins), chunk_rows):
                    block = np.asarray(scores[start:start + chunk_rows], dtype=np.float64)
                    yield (1.0 / (1.0 + np.exp(-block))) if transform == "sigmoid" else block
            if canonical_format == "hdf5_matrix":
                class BlockSource:
                    def __getitem__(self, item):
                        block = np.asarray(scores[item], dtype=np.float64)
                        return (1.0 / (1.0 + np.exp(-block))) if transform == "sigmoid" else block
                _write_matrix(path, proteins, terms, BlockSource(), score_semantics=score_semantics, output_stage=output_stage, chunk_rows=chunk_rows)
                count = len(proteins) * len(terms)
            else:
                def rows():
                    for start, block in zip(range(0, len(proteins), chunk_rows), blocks()):
                        for protein, values in zip(proteins[start:start + len(block)], block):
                            for term, score in zip(terms, values): yield protein, term, float(score)
                count = _write_rows(path, rows())
        events = ({"event": "sigmoid"},) if transform == "sigmoid" else ()
        return AdaptResult(path, score_semantics, output_stage, "hdf5_matrix", count, len(proteins), len(terms), events, canonical_format)


class DeepFRIJSONAdapter:
    name = "deepfri-json"
    version = "1"
    description = "DeepFRI full probability JSON containing pdb_chains, goterms, and Y_hat."

    def adapt(self, request: AdaptRequest) -> AdaptResult:
        payload = json.loads(request.input_path.read_text(encoding="utf-8"))
        protein_key = str(option(request.options, "protein_key", "pdb_chains")); term_key = str(option(request.options, "term_key", "goterms")); score_key = str(option(request.options, "score_key", "Y_hat"))
        try: proteins, terms, scores = list(map(str, payload[protein_key])), list(map(str, payload[term_key])), payload[score_key]
        except KeyError as exc: raise ModelAdapterError(f"DeepFRI JSON key missing: {exc}") from exc
        if len(scores) != len(proteins) or any(len(row) != len(terms) for row in scores): raise ModelAdapterError("Y_hat shape does not match pdb_chains/goterms")
        if len(set(proteins)) != len(proteins) or len(set(terms)) != len(terms): raise ModelAdapterError("DeepFRI protein and term axes must be unique")
        canonical_format = _requested_format(request, matrix_default=True); path = _matrix_output(request) if canonical_format == "hdf5_matrix" else _output(request)
        if canonical_format == "hdf5_matrix":
            values = np.asarray(scores, dtype=np.float32); _write_matrix(path, proteins, terms, values, score_semantics="probability", output_stage="pre_hierarchy")
            count = len(proteins) * len(terms)
        else: count = _write_rows(path, ((p, t, float(s)) for p, row in zip(proteins, scores) for t, s in zip(terms, row)))
        return AdaptResult(path, "probability", "pre_hierarchy", "deepfri_probability_json", count, len(proteins), len(terms), canonical_format=canonical_format)


class PandasHDFLogitsAdapter:
    name = "protnote-logits"
    version = "1"
    description = "Pandas HDF logits frame; applies the declared sigmoid conversion."

    def adapt(self, request: AdaptRequest) -> AdaptResult:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ModelAdapterError("protnote-logits requires pandas and PyTables") from exc
        key = str(option(request.options, "key", "logits_df")); frame = pd.read_hdf(request.input_path, key=key)
        proteins, terms = list(map(str, frame.index)), list(map(str, frame.columns)); values = np.asarray(frame.values, dtype=np.float64); values = 1.0 / (1.0 + np.exp(-values))
        if len(set(proteins)) != len(proteins) or len(set(terms)) != len(terms): raise ModelAdapterError("ProtNote protein and term axes must be unique")
        canonical_format = _requested_format(request, matrix_default=True); path = _matrix_output(request) if canonical_format == "hdf5_matrix" else _output(request)
        if canonical_format == "hdf5_matrix": _write_matrix(path, proteins, terms, values, score_semantics="probability", output_stage="pre_hierarchy"); count = len(proteins) * len(terms)
        else: count = _write_rows(path, ((p, t, float(s)) for p, row in zip(proteins, values) for t, s in zip(terms, row)))
        return AdaptResult(path, "probability", "pre_hierarchy", "pandas_hdf_logits", count, len(proteins), len(terms), ({"event": "sigmoid"},), canonical_format)
