"""Frozen ``goaudit`` command surface."""
from __future__ import annotations
import argparse,json,logging,sys
from dataclasses import replace
from pathlib import Path
from .config import ConfigError,load_config
from .engine import run_audit
from .model_adapters import ModelAdapterError,builtin_registry,load_plugins,run_adapter
from .report import render_existing
from .verdict import EXIT_VALIDATION,exit_code

def common(parser):
 parser.add_argument("--dry-run",action="store_true");parser.add_argument("--strict",action="store_true");parser.add_argument("--seed",type=int);parser.add_argument("--workers",type=int,default=1);parser.add_argument("--log-level",default="WARNING",choices=["DEBUG","INFO","WARNING","ERROR"]);return parser
def parser():
 p=argparse.ArgumentParser(prog="goaudit");s=p.add_subparsers(dest="command",required=True)
 q=common(s.add_parser("init"));q.add_argument("--output",required=True)
 q=common(s.add_parser("list-adapters"));q.add_argument("--plugin",action="append",default=[])
 q=common(s.add_parser("adapt"));q.add_argument("--adapter",required=True);q.add_argument("--input",required=True);q.add_argument("--out",required=True);q.add_argument("--option",action="append",default=[]);q.add_argument("--plugin",action="append",default=[])
 q=common(s.add_parser("adapt-audit"));q.add_argument("--adapter",required=True);q.add_argument("--input",required=True);q.add_argument("--contract",required=True);q.add_argument("--out",required=True);q.add_argument("--option",action="append",default=[]);q.add_argument("--plugin",action="append",default=[])
 for name in ("validate","semantics","threshold","audit"):
  q=common(s.add_parser(name));q.add_argument("--contract",required=True);q.add_argument("--out",required=True)
 q=common(s.add_parser("render"));q.add_argument("--audit",required=True);q.add_argument("--format",default="markdown,html")
 return p
def template():
 return """# goaudit.contract.v1; replace paths before use
schema_version: goaudit.contract.v1
audit_id: my-audit
created_utc: 2026-10-08T00:00:00Z
claim_scope: both
random_seed: 0
inputs_hash_policy: sha256
predictions: {path: scores.tsv, format: long_tsv, protein_field: protein_id, term_field: go_id, score_field: score, duplicate_policy: error, absent_term_score: 0.0, score_dtype: float64, allowed_range: [0.0, 1.0]}
ontology: {path: go.obo, format: obo, release: unspecified, relations: [is_a, part_of], reflexive_closure: true, direction: child_to_parent, namespace_roots: {}, alt_id_policy: resolve, obsolete_policy: drop, namespace_policy: close_within_namespace}
evaluation: {prediction_closure: ancestor, truth_closure: ancestor, root_policy: exclude, term_universe: emitted, universe_label_dependence: forbidden, comparison: greater_equal, threshold_representation: float64_direct, threshold_grid: {type: explicit, values: [0.5]}, precision_eligibility: predicted_proteins, recall_eligibility: truth_bearing_proteins, averaging: both}
external_evaluator: {mode: none, version: unspecified, input_contract: raw_scores}
threshold_analysis: {enabled: false}
"""
def main(argv=None):
 args=parser().parse_args(argv);logging.basicConfig(level=getattr(logging,args.log_level))
 try:
  if args.command=="init":
   if not args.dry_run:Path(args.output).write_text(template())
   print(json.dumps({"command":"init","output":str(Path(args.output).resolve()),"dry_run":args.dry_run}));return 0
  if args.command=="render":
   formats=set(args.format.split(","));unknown=formats-{"markdown","html"}
   if unknown:raise ConfigError(f"unsupported render formats: {sorted(unknown)}")
   artifacts={} if args.dry_run else render_existing(Path(args.audit).resolve(),formats);print(json.dumps({"command":"render","artifacts":artifacts},indent=2));return 0
  if args.command in {"list-adapters","adapt","adapt-audit"}:
   registry=builtin_registry();origins=load_plugins(registry,args.plugin)
   if args.command=="list-adapters":print(json.dumps({"adapters":registry.describe(),"plugins":origins},indent=2));return 0
   options={}
   for item in args.option:
    if "=" not in item:raise ConfigError("--option must use KEY=VALUE")
    key,value=item.split("=",1)
    if not key or key in options:raise ConfigError("adapter option keys must be nonempty and unique")
    try:options[key]=json.loads(value)
    except json.JSONDecodeError:options[key]=value
   if args.dry_run:
    result={"command":args.command,"adapter":args.adapter,"input":str(Path(args.input).resolve()),"out":str(Path(args.out).resolve()),"options":options,"dry_run":True}
   elif args.command=="adapt":result=run_adapter(registry,args.adapter,Path(args.input),Path(args.out),options,origins)
   else:
    root=Path(args.out).resolve()
    if root.exists():raise FileExistsError(root)
    root.mkdir(parents=True)
    adapted=run_adapter(registry,args.adapter,Path(args.input),root/"adapted",options,origins)
    base=load_config(args.contract,strict=args.strict); canonical=adapted["manifest"]["canonical"]
    prediction=replace(base.predictions,path=root/"adapted"/canonical["path"],format=canonical["format"],protein_field="protein_id",term_field="go_id",score_field="score")
    audit_config=replace(base,predictions=prediction)
    audit=run_audit(audit_config,mode="audit",write_outputs=True,output_dir=root/"audit")
    result={"command":"adapt-audit","adapter":adapted,"audit_summary":audit["summary"],"root":str(root)}
   print(json.dumps(result,indent=2,sort_keys=True));return exit_code(result["audit_summary"]["verdict"] if args.command=="adapt-audit" else {"input_integrity":"PASS","bc_identity":"PASS","external_equivalence":"NOT_AUDITABLE","adapter_failed":False}) if args.command=="adapt-audit" else 0
  config=load_config(args.contract,strict=args.strict)
  if args.seed is not None and args.seed!=config.random_seed:raise ConfigError("--seed must match contract random_seed")
  if args.workers<1:raise ConfigError("--workers must be >=1")
  result=run_audit(config,mode=args.command,write_outputs=not args.dry_run,output_dir=Path(args.out).resolve());print(json.dumps(result["summary"] if args.command!="validate" else {"audit_id":config.audit_id,"input_integrity":result["verdict"]["input_integrity"],"validation":result["validation"]},indent=2,sort_keys=True,allow_nan=False));return exit_code(result["verdict"],args.strict)
 except (ConfigError,ModelAdapterError,FileNotFoundError,FileExistsError,ValueError) as exc:print(f"goaudit: {exc}",file=sys.stderr);return EXIT_VALIDATION
if __name__=="__main__":raise SystemExit(main())
