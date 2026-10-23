"""Frozen R043-A verdict fields, gates, and stable exit codes."""
from __future__ import annotations
from typing import Any
EXIT_OK=0; EXIT_VALIDATION=2; EXIT_CANONICAL=3; EXIT_UNRESOLVED=4; EXIT_ADAPTER=5
GUARD_CANONICAL="DO_NOT_ATTRIBUTE_CANONICALIZATION_AS_METHOD_GAIN"
GUARD_OFFICIAL="DO_NOT_CLAIM_OFFICIAL_EQUIVALENCE"
GUARD_ORACLE="DO_NOT_USE_TARGET_ORACLE_FOR_SELECTION"
GUARD_LABEL_UNIVERSE="TERM_UNIVERSE_LABEL_DEPENDENT"
GUARD_ANNOTATION="ANNOTATION_INCOMPLETENESS_LIMITS_PRECISION"
GUARD_THRESHOLD="NO_UNIFORM_THRESHOLD_POLICY"

def make_verdict(*,input_integrity:str,bc_identity:str,external_observability:str,external_equivalence:str,attributed_axes:list[str]|None=None,threshold_effect:str="NOT_RUN",threshold_winner:str="NOT_TESTED",deployment_risk:str="NOT_CONFIGURED",claim_guard:list[str]|None=None,controlled_guards:list[str]|None=None,context_guards:list[str]|None=None,adapter_failed:bool=False)->dict[str,Any]:
 context=sorted(set(context_guards if context_guards is not None else (claim_guard or [])));controlled=sorted(set(controlled_guards or []))
 return {"input_integrity":input_integrity,"bc_identity":bc_identity,"external_observability":external_observability,"external_equivalence":external_equivalence,"attributed_axes":sorted(attributed_axes or []),"threshold_effect":threshold_effect,"threshold_winner":threshold_winner,"deployment_risk":deployment_risk,"controlled_guards":controlled,"context_guards":context,"claim_guard":sorted(set(controlled+context)),"adapter_failed":adapter_failed}

def exit_code(verdict:dict[str,Any],strict:bool=False)->int:
 if verdict["input_integrity"]=="FAIL": return EXIT_VALIDATION
 if verdict["bc_identity"]=="FAIL": return EXIT_CANONICAL
 if verdict.get("adapter_failed"): return EXIT_ADAPTER
 if verdict["external_equivalence"]=="UNRESOLVED": return EXIT_UNRESOLVED
 if strict and (verdict["input_integrity"]=="WARN" or verdict["external_observability"] in {"AGGREGATE_ONLY","NONE"}): return EXIT_VALIDATION
 return EXIT_OK

def controlled_gates(metrics:dict[str,float|bool|int])->dict[str,Any]:
 required={"pair_difference","exact_count_match","max_metric_error","canonicalization_pass","threshold_mismatch_rate","plateau_mismatch_rate","bootstrap_frequency_mismatch_rate","detection_sensitivity","null_specificity","axis_accuracy","min_axis_precision","min_axis_recall","false_attribution_rate","x01_correct","claim_guard_accuracy","product_gate"}
 if not required<=set(metrics): return {"status":"NOT_RUN","reason":"formal controlled-simulation metrics unavailable"}
 correctness=metrics["pair_difference"]==0 and bool(metrics["exact_count_match"]) and float(metrics["max_metric_error"])<=1e-12 and bool(metrics["canonicalization_pass"]) and all(float(metrics[k])==0 for k in ("threshold_mismatch_rate","plateau_mismatch_rate","bootstrap_frequency_mismatch_rate"))
 detection=float(metrics["detection_sensitivity"])>=.99 and float(metrics["null_specificity"])>=.99 and float(metrics["axis_accuracy"])>=.95 and float(metrics["min_axis_precision"])>=.90 and float(metrics["min_axis_recall"])>=.90 and float(metrics["false_attribution_rate"])<=.01 and bool(metrics["x01_correct"]) and float(metrics["claim_guard_accuracy"])==1.0
 product=bool(metrics["product_gate"]); passed=correctness and detection and product
 return {"status":"MVP_VALIDATED_CONTROLLED" if passed else "FAILED","correctness_gate":correctness,"detection_gate":detection,"integrity_product_gate":product,"pass":passed}
