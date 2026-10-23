"""Pure, shared-object Markdown/HTML renderer and frozen artifact tree."""
from __future__ import annotations
import html,json
from pathlib import Path
from typing import Any
from .io import sha256,write_csv,write_json

CSV_SPECS={
 "validation.csv":("validation",["check","severity","object","count","examples","resolved"]),
 "pair_digests.csv":("pair_digests",["threshold","pipeline","pair_sha256","pairs"]),
 "semantic_metrics.csv":("semantic_metrics",["threshold","pipeline","protein_precision","protein_recall","protein_f1","micro_precision","micro_recall","micro_f1","coverage","predicted_pairs","mean_predicted_terms","tp","fp","fn"]),
 "bc_mismatches.csv":("bc_mismatches",["threshold","protein_id","go_id","difference"]),
 "external_discrepancies.csv":("external_discrepancies",["threshold","raw_difference_pairs","closed_difference_pairs","adapter_pair_sha256"]),
 "attribution_matrix.csv":("attribution_matrix",["axis_set","difference_pairs","reconciles"]),
 "threshold_curves.csv":("threshold_curves",["partition","policy","threshold","protein_precision","protein_recall","protein_f1","micro_precision","micro_recall","micro_f1","coverage","predicted_pairs","mean_predicted_terms","tp","fp","fn"]),
 "threshold_bootstrap.csv":("threshold_bootstrap",["policy","draw","threshold"]),
 "threshold_summary.csv":("threshold_summary",["policy","selected_threshold","low","high","width","points","median","sd","iqr","q025","q975","frequency_json"]),
 "effect_attribution.csv":("effect_attribution",["threshold","metric","closure_evaluator_effect","operator_residual","label"]),
 "deployment_risk.csv":("deployment_risk",["policy","reference","precision_difference","coverage_difference","inflation","abstention_increase","pass"]),
}
def headline(verdict):return f"GO audit verdict: {verdict['external_equivalence']}; input {verdict['input_integrity']}; B/C {verdict['bc_identity']}."
def markdown(verdict):
 h=headline(verdict)
 return f"# GO Audit Report\n\n{h}\n\nSource: [verdict.json](verdict.json); contract: [resolved_contract.json](resolved_contract.json).\n\n## Controlled guards\n\n"+"\n".join(f"- `{x}`" for x in verdict.get("controlled_guards",[]))+"\n\n## Context guards\n\n"+"\n".join(f"- `{x}`" for x in verdict.get("context_guards",[]))+"\n"
def html_report(verdict):
 h=html.escape(headline(verdict)); payload=html.escape(json.dumps(verdict,sort_keys=True))
 return f"<!doctype html><html><head><meta charset='utf-8'><title>GO Audit</title><style>body{{font-family:system-ui;max-width:900px;margin:2rem auto}}code{{white-space:pre-wrap}}</style></head><body><h1>GO Audit Report</h1><p>{h}</p><p>Source: <a href='verdict.json'>verdict.json</a>; contract: <a href='resolved_contract.json'>resolved_contract.json</a>.</p><h2>Machine verdict</h2><code>{payload}</code></body></html>\n"
def render_existing(verdict_path:Path,formats:set[str])->dict[str,str]:
 verdict=json.loads(verdict_path.read_text()); out={}
 if "markdown" in formats: p=verdict_path.parent/"report.md";p.write_text(markdown(verdict));out["markdown"]=str(p)
 if "html" in formats:p=verdict_path.parent/"report.html";p.write_text(html_report(verdict));out["html"]=str(p)
 return out
def report_consistency(root:Path)->dict[str,Any]:
 verdict=json.loads((root/"verdict.json").read_text());h=headline(verdict);return {"headline":h,"markdown_matches":h in (root/"report.md").read_text(),"html_matches":html.escape(h) in (root/"report.html").read_text()}
def write_report(root:Path,result:dict[str,Any])->dict[str,str]:
 root.mkdir(parents=True,exist_ok=True);write_json(root/"resolved_contract.json",result["resolved_contract"]);write_json(root/"provenance.json",result["provenance"]);write_json(root/"canonical_inputs.json",result["summary"]["canonical_inputs"]);write_json(root/"idempotence.json",result["idempotence"]);write_json(root/"verdict.json",result["verdict"]);write_json(root/"audit_summary.json",result["summary"]);
 for filename,(key,fields) in CSV_SPECS.items():write_csv(root/filename,result[key],fields)
 render_existing(root/"verdict.json",{"markdown","html"}); consistency=report_consistency(root)
 if not consistency["markdown_matches"] or not consistency["html_matches"]:raise AssertionError("report/verdict disagreement")
 write_json(root/"report_consistency.json",consistency); names=["resolved_contract.json","provenance.json","validation.csv","canonical_inputs.json",*CSV_SPECS.keys(),"idempotence.json","verdict.json","audit_summary.json","report.md","report.html","report_consistency.json"];write_json(root/"manifest.json",{"artifacts":[{"path":name,"sha256":sha256(root/name),"bytes":(root/name).stat().st_size} for name in names]});return {name:str(root/name) for name in names+["manifest.json"]}
