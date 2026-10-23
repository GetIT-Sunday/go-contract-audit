"""Generic R043-A stage-1 orchestration; no project-specific imports."""
from __future__ import annotations
import json,platform,sys
from pathlib import Path
from typing import Any
import numpy as np
from . import __version__
from .adapters import AdapterError,call_adapter
from .config import AuditConfig
from .io import read_groups,read_id_set,read_scores,read_truth,sha256
from .metrics import evaluate,fixed_policy_bootstrap
from .ontology import parse_obo
from .report import write_report
from .semantics import ancestor_max,close_sets,filter_sets,namespace_view,pair_digest,symmetric_differences,threshold_sets
from .attribution import attribute_external
from .validate import validation_rows
from .verdict import GUARD_ANNOTATION,GUARD_CANONICAL,GUARD_LABEL_UNIVERSE,GUARD_OFFICIAL,GUARD_ORACLE,GUARD_THRESHOLD,controlled_gates,make_verdict

def _universe(config,ontology,terms):
 if config.evaluation.term_universe=="emitted": result=set(terms)
 elif config.evaluation.term_universe=="emitted_plus_ancestors": result=set(terms)|set().union(*(ontology.ancestors(x) for x in terms))
 elif config.evaluation.term_universe=="ontology_namespace": result=set(ontology.parents)
 else: result=read_id_set(config.evaluation.explicit_term_file)
 if config.evaluation.root_policy=="exclude": result-=set(config.ontology.namespace_roots.values())
 return result
def _eligibility(config): return ("all" if config.evaluation.precision_eligibility=="all_proteins" else "predicted","all" if config.evaluation.recall_eligibility=="all_proteins" else "truth")
def _provenance(config):
 paths={"contract":config.config_path,"predictions":config.predictions.path,"ontology":config.ontology.path}
 if config.truth:paths["truth"]=config.truth.path
 for name in ("calibration_split","target_split","group_file"):
  path=getattr(config.threshold_analysis,name);
  if path:paths[name]=path
 return [{"role":k,"path":str(v),"sha256":sha256(v),"bytes":v.stat().st_size} for k,v in sorted(paths.items())]
def run_audit(config:AuditConfig,*,mode:str="audit",write_outputs:bool=True,output_dir:Path|None=None)->dict[str,Any]:
 for p in [config.predictions.path,config.ontology.path]+([config.truth.path] if config.truth else []):
  if not p.is_file():raise FileNotFoundError(p)
 ontology=parse_obo(config.ontology.path,config.ontology.relations); data=read_scores(config.predictions,ontology,config.ontology.alt_id_policy,config.ontology.obsolete_policy)
 if not data.proteins or not data.terms:raise ValueError("no valid prediction rows")
 raw_truth,truth_audit=read_truth(config.truth,data.proteins,ontology,config.ontology.alt_id_policy,config.ontology.obsolete_policy); validation=validation_rows(config,data,ontology,truth_audit); integrity="FAIL" if any(x["severity"]=="ERROR" and not x["resolved"] for x in validation) else ("WARN" if any(x["severity"]=="WARN" for x in validation) else "PASS")
 graph_ontology=namespace_view(ontology,set(config.ontology.namespace_roots)) if config.ontology.namespace_policy=="close_within_namespace" else ontology
 universe=_universe(config,graph_ontology,data.terms); output_terms=tuple(sorted(universe)); scores=data.matrix; closed=ancestor_max(scores,list(data.terms),list(output_terms),graph_ontology); twice=ancestor_max(closed,list(output_terms),list(output_terms),graph_ontology); score_idem=bool(np.array_equal(closed,twice)); pe,re=_eligibility(config); truth=close_sets(raw_truth,graph_ontology) if config.evaluation.truth_closure=="ancestor" and config.truth and config.truth.semantics=="direct" else raw_truth; truth=filter_sets(truth,universe)
 digests=[];semantic=[];mismatches=[];semantic_metrics=[];canonical={};raw_sets={};closed_sets={}; effect=[]
 for tau in config.evaluation.threshold_grid.values:
  ar=threshold_sets(scores,list(data.terms),tau,config.evaluation.comparison); a=filter_sets(ar,universe); b=filter_sets(close_sets(ar,graph_ontology),universe); c=threshold_sets(closed,list(output_terms),tau,config.evaluation.comparison); b2=filter_sets(close_sets(b,graph_ontology),universe); raw_sets[tau]=a;closed_sets[tau]=b;canonical[tau]=b;diff=symmetric_differences(list(data.proteins),b,c);mismatches += [{"threshold":tau,**x} for x in diff]
  for pipeline,pred in (("A",a),("B",b),("C",c)):
   metric=evaluate(pred,truth,pe,re) if config.truth else {}; digests.append({"threshold":tau,"pipeline":pipeline,"pair_sha256":pair_digest(list(data.proteins),pred),"pairs":sum(map(len,pred))}); semantic_metrics.append({"threshold":tau,"pipeline":pipeline,**metric})
  semantic.append({"threshold":tau,"B_C_equal":b==c,"B_C_symmetric_difference_pairs":len(diff),"set_idempotent":b==b2});
  if config.truth:
   ma=evaluate(a,truth,pe,re);mb=evaluate(b,truth,pe,re);mc=evaluate(c,truth,pe,re);effect.append({"threshold":tau,"metric":"protein_f1","closure_evaluator_effect":mb["protein_f1"]-ma["protein_f1"],"operator_residual":mc["protein_f1"]-mb["protein_f1"],"label":"bookkeeping_not_causal"})
 bc=sum(x["B_C_symmetric_difference_pairs"] for x in semantic); set_idem=all(x["set_idempotent"] for x in semantic); adapter_rows=[];adapter_failed=False;external="NOT_AUDITABLE";observable="NONE";axes=[]
 if config.external_evaluator.mode=="python_adapter":
  observable="PAIRWISE"
  try:
   result=call_adapter(config.external_evaluator,proteins=list(data.proteins),terms=list(data.terms),scores=scores,thresholds=config.evaluation.threshold_grid.values,contract=config.resolved_dict()); match_raw=match_closed=True
   observed_truth=[set(x) for x in result.get("truth",truth)]; truth_matches=observed_truth==truth
   for tau in config.evaluation.threshold_grid.values:
    supplied=result["predictions"].get(tau,result["predictions"].get(str(tau))); candidate=[set(x) for x in supplied]; dr=sum(len(x^y) for x,y in zip(raw_sets[tau],candidate));dc=sum(len(x^y) for x,y in zip(closed_sets[tau],candidate));match_raw&=dr==0 and truth_matches;match_closed&=dc==0 and truth_matches;adapter_rows.append({"threshold":tau,"raw_difference_pairs":dr,"closed_difference_pairs":dc,"adapter_pair_sha256":pair_digest(list(data.proteins),candidate)})
   if match_raw: external="RAW"
   elif match_closed: external="CLOSED"
   else:
    observed={"predictions":{float(t):[set(x) for x in result["predictions"].get(t,result["predictions"].get(str(t)))] for t in config.evaluation.threshold_grid.values},"truth":observed_truth}
    attribution=attribute_external(observed,config=config,ontology=ontology,proteins=data.proteins,terms=data.terms,scores=scores,raw_truth=raw_truth,closed_truth=truth,canonical_universe=universe);external={"ATTRIBUTED":"ATTRIBUTED","AMBIGUOUS":"AMBIGUOUS","UNRESOLVED":"UNRESOLVED"}.get(attribution["verdict"],"UNRESOLVED");axes=attribution["minimal_axis_sets"][0] if len(attribution["minimal_axis_sets"])==1 else [];adapter_rows.extend(attribution["rows"])
  except Exception:adapter_failed=True;external="UNRESOLVED"
 elif config.external_evaluator.mode=="aggregate_file":observable="AGGREGATE_ONLY";external="NOT_AUDITABLE"
 guards=[GUARD_CANONICAL,GUARD_OFFICIAL];
 if config.truth and config.truth.negative_semantics=="unknown":guards.append(GUARD_ANNOTATION)
 if config.evaluation.universe_label_dependence=="declared_diagnostic":guards.append(GUARD_LABEL_UNIVERSE)
 threshold_rows=[];threshold_boot=[];threshold_summary=[];risk=[];threshold_effect="NOT_RUN"
 if mode in {"threshold","audit"} and config.threshold_analysis.enabled and integrity!="FAIL":
  target=read_id_set(config.threshold_analysis.target_split);ti=[i for i,p in enumerate(data.proteins) if p in target];groups=read_groups(config.threshold_analysis.group_file if config.threshold_analysis.grouping=="cluster_file" else None,data.proteins); target_groups=[groups[i] for i in ti]; target_truth=[truth[i] for i in ti]
  # Stage 1 evaluates only thresholds explicitly frozen in the contract. It does
  # not maximize calibration or target F1. Calibration-stage policy selection
  # remains reserved for the controlled simulation runner.
  for tau in config.evaluation.threshold_grid.values:
   pred=filter_sets(threshold_sets(closed[ti],list(output_terms),tau,config.evaluation.comparison),universe);metric=evaluate(pred,target_truth,pe,re);bootstrap=fixed_policy_bootstrap(pred,target_truth,target_groups,config.threshold_analysis.bootstrap_draws,config.random_seed,.95,pe,re)
   threshold_rows.append({"partition":"target_fixed","policy":"declared_fixed","threshold":tau,**metric});threshold_summary.append({"policy":"declared_fixed","selected_threshold":tau,"low":tau,"high":tau,"width":0.0,"points":1,"median":tau,"sd":0.0,"iqr":0.0,"q025":tau,"q975":tau,"frequency_json":json.dumps({str(tau):config.threshold_analysis.bootstrap_draws}),"selection_status":"FIXED_CONTRACT_VALUE"});threshold_boot += [{"policy":"declared_fixed","draw":draw,"threshold":tau,"metric_json":json.dumps({name:value["mean"] for name,value in bootstrap.items()},sort_keys=True)} for draw in range(config.threshold_analysis.bootstrap_draws)]
  threshold_effect="NOT_RUN";guards += [GUARD_ORACLE]
 risk_status="NOT_CONFIGURED" if not config.deployment_risk or not risk else ("PASS" if all(x["pass"] for x in risk) else "FAIL")
 controlled_guards=[]
 if "term_universe_label_dependence" in axes:controlled_guards.append(GUARD_LABEL_UNIVERSE)
 if "prediction_closure" in axes:controlled_guards.append(GUARD_CANONICAL)
 verdict=make_verdict(input_integrity=integrity,bc_identity="PASS" if bc==0 and set_idem and score_idem else "FAIL",external_observability=observable,external_equivalence=external,attributed_axes=axes,threshold_effect=threshold_effect,threshold_winner="NONE" if threshold_effect!="NOT_RUN" else "NOT_TESTED",deployment_risk=risk_status,controlled_guards=controlled_guards,context_guards=guards,adapter_failed=adapter_failed)
 summary={"audit_id":config.audit_id,"verdict":verdict,"controlled_validation_gate":controlled_gates({}),"canonical_inputs":{"proteins":len(data.proteins),"terms":len(data.terms),"matrix_sha256":data.audit["canonical_matrix_sha256"],"normalization_events":list(data.normalization_events)},"semantic_equivalence":{"thresholds":len(semantic),"bc_mismatch_pairs":bc,"set_idempotent":set_idem,"score_idempotent":score_idem},"claim_boundary":"Controlled software audit only; no biological utility or official-evaluator claim.","protocol_hashes":{"architecture":"bd17f3478e2af9e03a9c03ac2762b6a54c72e21487c2591655fff65ba4af591f","protocol":"9a44f079f71d11ade054a0e2102735acbc18da36801aca073912e874cdb6e974","simulation_design":"01e60912074ca32277e295d79cdfc4ea6c1e700cff95f82004a73130cf7963f7","fixture_schema":"b16d55f39315a9253d01172e1e1d3d0b57cf74bdc6aaf30f6c0a1b803c278e89"},"runtime":{"tool_version":__version__,"python":sys.version.split()[0],"platform":platform.platform()}}
 result={"summary":summary,"resolved_contract":config.resolved_dict(),"provenance":_provenance(config),"validation":validation,"pair_digests":digests,"semantic_metrics":semantic_metrics,"bc_mismatches":mismatches,"external_discrepancies":adapter_rows,"attribution_matrix":[],"idempotence":{"set":set_idem,"score":score_idem},"threshold_curves":threshold_rows,"threshold_bootstrap":threshold_boot,"threshold_summary":threshold_summary,"effect_attribution":effect,"deployment_risk":risk,"verdict":verdict}
 if write_outputs:result["artifacts"]=write_report(output_dir or Path("audit"),result)
 return result
