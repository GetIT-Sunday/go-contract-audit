"""Canonical long-table input, split/group readers, and artifact writers."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .config import PredictionSpec, TruthSpec
from .ontology import Ontology


@dataclass(frozen=True)
class CanonicalScores:
    proteins: tuple[str, ...]
    terms: tuple[str, ...]
    matrix: np.ndarray
    audit: Mapping[str, Any]
    normalization_events: tuple[Mapping[str, Any], ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_matrix_digest(proteins: Iterable[str], terms: Iterable[str], matrix: np.ndarray) -> str:
    digest = hashlib.sha256(); protein_list, term_list = list(proteins), list(terms)
    for i, protein in enumerate(protein_list):
        for j, term in enumerate(term_list):
            digest.update(f"{protein}\t{term}\t{float(matrix[i,j]).hex()}\n".encode())
    return digest.hexdigest()


def read_scores(spec: PredictionSpec, ontology: Ontology, alt_policy: str, obsolete_policy: str) -> CanonicalScores:
    if spec.format == "hdf5_matrix": return _read_hdf5_scores(spec, ontology, alt_policy, obsolete_policy)
    if spec.format != "long_tsv": raise ValueError(f"input adapter for {spec.format} unavailable in stage-1")
    required = {spec.protein_field, spec.term_field, spec.score_field}; values: dict[tuple[str, str], float] = {}
    same = conflict = unknown = obsolete = aliases = out_range = nan = infinity = 0
    with spec.path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not required <= set(reader.fieldnames or ()): raise ValueError(f"score table requires {sorted(required)}")
        for row in reader:
            protein, raw_term = row[spec.protein_field].strip(), row[spec.term_field].strip()
            try: score = float(row[spec.score_field])
            except ValueError as exc: raise ValueError(f"invalid score for {protein}/{raw_term}") from exc
            nan += int(np.isnan(score)); infinity += int(np.isinf(score))
            if not np.isfinite(score): continue
            out_range += int(not spec.allowed_range[0] <= score <= spec.allowed_range[1])
            if not spec.allowed_range[0] <= score <= spec.allowed_range[1]: continue
            is_alias = raw_term in ontology.alt_ids; aliases += int(is_alias)
            if is_alias and alt_policy == "error": unknown += 1; continue
            term = ontology.canonical(raw_term) if is_alias and alt_policy == "resolve" else raw_term
            if is_alias and alt_policy == "retain":
                # Retained aliases are explicit identifiers with the canonical term's graph position.
                ontology.parents.setdefault(raw_term, ontology.parents[ontology.canonical(raw_term)])
                ontology.namespaces.setdefault(raw_term, ontology.namespaces.get(ontology.canonical(raw_term), ""))
            if term not in ontology.parents: unknown += 1; continue
            if term in ontology.obsolete:
                obsolete += 1
                if obsolete_policy == "replaced_by" and term in ontology.replacements: term = ontology.replacements[term]
                elif obsolete_policy in {"drop", "error"}: continue
            key = (protein, term)
            if key in values:
                same += int(values[key] == score); conflict += int(values[key] != score)
                if spec.duplicate_policy == "max": values[key] = max(values[key], score)
            else: values[key] = score
    fatal_duplicates = spec.duplicate_policy == "error" and same + conflict > 0
    events = ({"event": "duplicate_max", "count": same + conflict},) if spec.duplicate_policy == "max" and same + conflict else ()
    proteins, terms = tuple(sorted({x[0] for x in values})), tuple(sorted({x[1] for x in values}))
    matrix = np.full((len(proteins), len(terms)), spec.absent_term_score, dtype=np.float64); pi = {x:i for i,x in enumerate(proteins)}; ti={x:i for i,x in enumerate(terms)}
    for (protein, term), score in values.items(): matrix[pi[protein], ti[term]] = score
    audit = {"rows_retained":len(values),"proteins":len(proteins),"terms":len(terms),"duplicate_identical":same,"duplicate_conflicting":conflict,"fatal_duplicates":fatal_duplicates,"unknown_terms":unknown,"obsolete_terms":obsolete,"fatal_obsolete":obsolete_policy=="error" and obsolete>0,"alt_id_rows":aliases,"fatal_alt_ids":alt_policy=="error" and aliases>0,"nan_scores":nan,"infinite_scores":infinity,"out_of_range_scores":out_range,"canonical_matrix_sha256":canonical_matrix_digest(proteins,terms,matrix)}
    return CanonicalScores(proteins, terms, matrix, audit, events)


def _read_hdf5_scores(spec: PredictionSpec, ontology: Ontology, alt_policy: str, obsolete_policy: str) -> CanonicalScores:
    try:
        import h5py
    except ImportError as exc:
        raise ValueError("hdf5_matrix input requires h5py") from exc
    with h5py.File(spec.path, "r") as handle:
        missing = {"protein_ids", "term_ids", "scores"} - set(handle)
        if missing: raise ValueError(f"HDF5 datasets missing: {sorted(missing)}")
        raw_proteins = [x.decode() if isinstance(x, bytes) else str(x) for x in handle["protein_ids"][:]]
        raw_terms = [x.decode() if isinstance(x, bytes) else str(x) for x in handle["term_ids"][:]]
        source = np.asarray(handle["scores"][:], dtype=np.float64)
    if source.shape != (len(raw_proteins), len(raw_terms)) or len(set(raw_proteins)) != len(raw_proteins) or len(set(raw_terms)) != len(raw_terms): raise ValueError("HDF5 score axes are invalid")
    unknown = obsolete = aliases = same = conflict = 0; groups: dict[str, list[int]] = {}
    for j, raw_term in enumerate(raw_terms):
        is_alias = raw_term in ontology.alt_ids; aliases += int(is_alias) * len(raw_proteins)
        if is_alias and alt_policy == "error": unknown += len(raw_proteins); continue
        term = ontology.canonical(raw_term) if is_alias and alt_policy == "resolve" else raw_term
        if term not in ontology.parents: unknown += len(raw_proteins); continue
        if term in ontology.obsolete:
            obsolete += len(raw_proteins)
            if obsolete_policy == "replaced_by" and term in ontology.replacements: term = ontology.replacements[term]
            elif obsolete_policy in {"drop", "error"}: continue
        groups.setdefault(term, []).append(j)
    proteins, terms = tuple(sorted(raw_proteins)), tuple(sorted(groups)); raw_index = {protein:index for index,protein in enumerate(raw_proteins)}; protein_order = np.asarray([raw_index[protein] for protein in proteins], dtype=np.int64)
    matrix = np.full((len(proteins), len(terms)), spec.absent_term_score, dtype=np.float64)
    for target, term in enumerate(terms):
        columns = groups[term]; values = source[:, columns]
        if len(columns) > 1:
            baseline = values[:, [0]]; same += int(np.count_nonzero(values[:, 1:] == baseline)); conflict += int(np.count_nonzero(values[:, 1:] != baseline))
        combined = np.max(values, axis=1) if spec.duplicate_policy == "max" else values[:, 0]
        matrix[:, target] = combined[protein_order]
    nan = int(np.count_nonzero(np.isnan(matrix))); infinity = int(np.count_nonzero(np.isinf(matrix)))
    out_range = int(np.count_nonzero(np.isfinite(matrix) & ((matrix < spec.allowed_range[0]) | (matrix > spec.allowed_range[1]))))
    invalid = ~np.isfinite(matrix) | (matrix < spec.allowed_range[0]) | (matrix > spec.allowed_range[1]); matrix[invalid] = spec.absent_term_score
    fatal_duplicates = spec.duplicate_policy == "error" and same + conflict > 0; events = ({"event":"duplicate_max","count":same+conflict},) if spec.duplicate_policy=="max" and same+conflict else ()
    audit={"rows_retained":int(matrix.size),"proteins":len(proteins),"terms":len(terms),"duplicate_identical":same,"duplicate_conflicting":conflict,"fatal_duplicates":fatal_duplicates,"unknown_terms":unknown,"obsolete_terms":obsolete,"fatal_obsolete":obsolete_policy=="error" and obsolete>0,"alt_id_rows":aliases,"fatal_alt_ids":alt_policy=="error" and aliases>0,"nan_scores":nan,"infinite_scores":infinity,"out_of_range_scores":out_range,"canonical_matrix_sha256":canonical_matrix_digest(proteins,terms,matrix)}
    return CanonicalScores(proteins,terms,matrix,audit,events)


def read_truth(spec: TruthSpec | None, proteins: tuple[str, ...], ontology: Ontology, alt_policy: str, obsolete_policy: str) -> tuple[list[set[str]], dict[str,int]]:
    if spec is None: return [set() for _ in proteins], {"rows":0,"unknown_proteins":0,"unknown_terms":0}
    if spec.format != "pair_tsv": raise ValueError(f"truth adapter for {spec.format} unavailable in stage-1")
    result={protein:set() for protein in proteins}; unknown_p=unknown_t=rows=0
    with spec.path.open(newline="",encoding="utf-8") as handle:
        reader=csv.DictReader(handle,delimiter="\t")
        if not {spec.protein_field,spec.term_field}<=set(reader.fieldnames or ()): raise ValueError("truth table lacks configured fields")
        for row in reader:
            rows+=1; protein=row[spec.protein_field].strip(); term=row[spec.term_field].strip()
            if protein not in result: unknown_p+=1; continue
            if term in ontology.alt_ids and alt_policy=="resolve": term=ontology.canonical(term)
            if term not in ontology.parents: unknown_t+=1; continue
            if term in ontology.obsolete:
                if obsolete_policy=="replaced_by" and term in ontology.replacements: term=ontology.replacements[term]
                elif obsolete_policy in {"drop","error"}: continue
            result[protein].add(term)
    return [result[p] for p in proteins], {"rows":rows,"unknown_proteins":unknown_p,"unknown_terms":unknown_t}


def read_id_set(path: Path) -> set[str]:
    result=set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value=line.split("\t")[0].strip()
        if value and value.lower() not in {"protein_id","id"}: result.add(value)
    return result


def read_groups(path: Path | None, proteins: tuple[str,...]) -> list[str]:
    if path is None: return list(proteins)
    mapping={}
    with path.open(newline="",encoding="utf-8") as handle:
        reader=csv.DictReader(handle,delimiter="\t")
        if not {"protein_id","cluster_id"}<=set(reader.fieldnames or ()): raise ValueError("group_file requires protein_id and cluster_id")
        for row in reader: mapping[row["protein_id"]]=row["cluster_id"]
    return [mapping.get(p,f"singleton:{p}") for p in proteins]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Mapping[str,Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(list(rows))
