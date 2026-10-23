"""Structured validation rows for the frozen product contract."""
from __future__ import annotations
from pathlib import Path
from .config import AuditConfig
from .io import CanonicalScores,read_id_set
from .ontology import Ontology,cycle_nodes

def validation_rows(config:AuditConfig,scores:CanonicalScores,ontology:Ontology,truth_audit:dict)->list[dict]:
 rows=[]
 def add(check,severity,obj,count,examples="",resolved=True):rows.append({"check":check,"severity":severity,"object":obj,"count":int(count),"examples":examples,"resolved":bool(resolved)})
 a=scores.audit; add("finite_scores","ERROR" if a["nan_scores"]+a["infinite_scores"] else "PASS","predictions",a["nan_scores"]+a["infinite_scores"],resolved=not(a["nan_scores"]+a["infinite_scores"])); add("score_range","ERROR" if a["out_of_range_scores"] else "PASS","predictions",a["out_of_range_scores"],resolved=not a["out_of_range_scores"]); add("duplicates","ERROR" if a["fatal_duplicates"] else ("WARN" if a["duplicate_identical"]+a["duplicate_conflicting"] else "PASS"),"predictions",a["duplicate_identical"]+a["duplicate_conflicting"],resolved=not a["fatal_duplicates"]); add("unknown_terms","WARN" if a["unknown_terms"] else "PASS","predictions",a["unknown_terms"]); add("ontology_cycle","ERROR" if cycle_nodes(ontology) else "PASS","ontology",len(cycle_nodes(ontology)),",".join(cycle_nodes(ontology)[:5]),not cycle_nodes(ontology)); add("unknown_truth_proteins","ERROR" if config.truth and config.truth.unknown_protein_policy=="error" and truth_audit["unknown_proteins"] else ("WARN" if truth_audit["unknown_proteins"] else "PASS"),"truth",truth_audit["unknown_proteins"],resolved=not(config.truth and config.truth.unknown_protein_policy=="error" and truth_audit["unknown_proteins"])); roots_missing=[x for x in config.ontology.namespace_roots.values() if x not in ontology.parents]; add("namespace_roots","ERROR" if roots_missing else "PASS","ontology",len(roots_missing),",".join(roots_missing),not roots_missing); add("threshold_grid","PASS","evaluation",0);
 if config.threshold_analysis.enabled:
  cal=read_id_set(config.threshold_analysis.calibration_split); target=read_id_set(config.threshold_analysis.target_split); overlap=cal&target; add("split_overlap","ERROR" if overlap else "PASS","threshold_analysis",len(overlap),",".join(sorted(overlap)[:5]),not overlap)
 return rows
