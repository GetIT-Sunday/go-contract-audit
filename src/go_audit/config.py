"""Frozen ``goaudit.contract.v1`` contract model and resolver."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "goaudit.contract.v1"
TOP_FIELDS = {
    "schema_version", "audit_id", "created_utc", "claim_scope",
    "random_seed", "inputs_hash_policy", "predictions", "truth",
    "ontology", "evaluation", "operators", "external_evaluator",
    "threshold_analysis", "deployment_risk",
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PredictionSpec:
    path: Path
    format: str = "long_tsv"
    protein_field: str = "protein_id"
    term_field: str = "go_id"
    score_field: str = "score"
    duplicate_policy: str = "error"
    absent_term_score: float = 0.0
    score_dtype: str = "float64"
    allowed_range: tuple[float, float] = (0.0, 1.0)


@dataclass(frozen=True)
class TruthSpec:
    path: Path
    format: str = "pair_tsv"
    semantics: str = "direct"
    negative_semantics: str = "unknown"
    evidence_filter: tuple[str, ...] = ()
    unknown_protein_policy: str = "error"
    protein_field: str = "protein_id"
    term_field: str = "go_id"


@dataclass(frozen=True)
class OntologySpec:
    path: Path
    format: str = "obo"
    release: str = "unspecified"
    relations: tuple[str, ...] = ("is_a", "part_of")
    reflexive_closure: bool = True
    direction: str = "child_to_parent"
    namespace_roots: Mapping[str, str] = field(default_factory=dict)
    alt_id_policy: str = "resolve"
    obsolete_policy: str = "drop"
    namespace_policy: str = "close_within_namespace"


@dataclass(frozen=True)
class ThresholdGridSpec:
    type: str = "explicit"
    values: tuple[float, ...] = (0.5,)


@dataclass(frozen=True)
class EvaluationSpec:
    prediction_closure: str = "ancestor"
    truth_closure: str = "ancestor"
    root_policy: str = "exclude"
    term_universe: str = "emitted"
    explicit_term_file: Path | None = None
    universe_label_dependence: str = "forbidden"
    comparison: str = "greater_equal"
    threshold_representation: str = "float64_direct"
    threshold_grid: ThresholdGridSpec = ThresholdGridSpec()
    precision_eligibility: str = "predicted_proteins"
    recall_eligibility: str = "truth_bearing_proteins"
    averaging: str = "both"


@dataclass(frozen=True)
class ExternalEvaluatorSpec:
    mode: str = "none"
    path: str | None = None
    version: str = "unspecified"
    input_contract: str = "raw_scores"
    pair_output: Path | None = None
    count_output: Path | None = None
    metric_output: Path | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ThresholdAnalysisSpec:
    enabled: bool = False
    calibration_split: Path | None = None
    target_split: Path | None = None
    grouping: str = "protein"
    group_file: Path | None = None
    policies: tuple[str, ...] = ("raw_calibrated", "closed_calibrated")
    target_score_field: str = "closed"
    selection_metric: str = "protein_f1"
    tie_break: str = "lowest_threshold"
    bootstrap_draws: int = 500
    plateau_tolerance_f1: float = 0.005
    target_oracle_diagnostic: bool = True


@dataclass(frozen=True)
class DeploymentRiskSpec:
    reference_pipeline: str
    precision_drop_budget: float
    coverage_drop_budget: float
    prediction_inflation_budget: float
    abstention_increase_budget: float


@dataclass(frozen=True)
class AuditConfig:
    config_path: Path
    schema_version: str
    audit_id: str
    created_utc: str
    claim_scope: str
    random_seed: int
    inputs_hash_policy: str
    predictions: PredictionSpec
    truth: TruthSpec | None
    ontology: OntologySpec
    evaluation: EvaluationSpec
    operators: Mapping[str, Mapping[str, Any]]
    external_evaluator: ExternalEvaluatorSpec
    threshold_analysis: ThresholdAnalysisSpec
    deployment_risk: DeploymentRiskSpec | None
    unknown_fields: tuple[str, ...] = ()

    def resolved_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("config_path")
        value.pop("unknown_fields")

        def convert(item: Any) -> Any:
            if isinstance(item, Path):
                return str(item)
            if isinstance(item, tuple):
                return [convert(x) for x in item]
            if isinstance(item, dict):
                return {key: convert(x) for key, x in item.items()}
            if isinstance(item, list):
                return [convert(x) for x in item]
            return item
        return convert(value)


def _map(value: Any, name: str, optional: bool = False) -> Mapping[str, Any]:
    if value is None and optional:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be an object")
    return value


def _unknown(value: Mapping[str, Any], allowed: set[str], name: str, strict: bool) -> tuple[str, ...]:
    result = tuple(sorted(set(value) - allowed))
    if strict and result:
        raise ConfigError(f"unknown {name} fields: {', '.join(result)}")
    return result


def _path(base: Path, value: Any, name: str, optional: bool = False) -> Path | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty path")
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _choice(value: Any, choices: set[str], name: str) -> str:
    if value not in choices:
        raise ConfigError(f"{name} must be one of {sorted(choices)}")
    return str(value)


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ConfigError("created_utc must include a timezone")
        return value.isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        raise ConfigError("created_utc must be RFC3339")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigError("created_utc must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ConfigError("created_utc must include a timezone")
    return value


def _read(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    elif path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise ConfigError("YAML contracts require PyYAML") from exc
        value = yaml.safe_load(text)
    else:
        raise ConfigError("contract must use .json, .yaml, or .yml")
    return _map(value, "contract")


def load_config(path: str | Path, *, strict: bool = True) -> AuditConfig:
    source = Path(path).expanduser().resolve()
    raw = _read(source)
    unknown: list[str] = list(_unknown(raw, TOP_FIELDS, "top-level", strict))
    required = {"schema_version", "audit_id", "created_utc", "claim_scope", "random_seed", "inputs_hash_policy", "predictions", "ontology", "evaluation"}
    missing = sorted(required - set(raw))
    if missing:
        raise ConfigError(f"missing required fields: {', '.join(missing)}")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION}")
    audit_id = raw["audit_id"]
    if not isinstance(audit_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", audit_id):
        raise ConfigError("audit_id contains unsupported characters")
    base = source.parent

    p = _map(raw["predictions"], "predictions")
    unknown += [f"predictions.{x}" for x in _unknown(p, {"path", "format", "protein_field", "term_field", "score_field", "duplicate_policy", "absent_term_score", "score_dtype", "allowed_range"}, "predictions", strict)]
    bounds = tuple(float(x) for x in p.get("allowed_range", [0.0, 1.0]))
    if len(bounds) != 2 or bounds[0] >= bounds[1]:
        raise ConfigError("predictions.allowed_range must be [low, high]")
    predictions = PredictionSpec(
        path=_path(base, p.get("path"), "predictions.path"),
        format=_choice(p.get("format", "long_tsv"), {"long_tsv", "long_parquet", "hdf5_matrix"}, "predictions.format"),
        protein_field=str(p.get("protein_field", "protein_id")), term_field=str(p.get("term_field", "go_id")), score_field=str(p.get("score_field", "score")),
        duplicate_policy=_choice(p.get("duplicate_policy", "error"), {"error", "max"}, "predictions.duplicate_policy"),
        absent_term_score=float(p.get("absent_term_score", 0.0)), score_dtype=_choice(p.get("score_dtype", "float64"), {"float64"}, "predictions.score_dtype"), allowed_range=bounds,
    )
    if predictions.absent_term_score != 0.0:
        raise ConfigError("MVP requires absent_term_score=0.0")

    truth = None
    if raw.get("truth") is not None:
        t = _map(raw["truth"], "truth")
        unknown += [f"truth.{x}" for x in _unknown(t, {"path", "format", "semantics", "negative_semantics", "evidence_filter", "unknown_protein_policy", "protein_field", "term_field"}, "truth", strict)]
        truth = TruthSpec(path=_path(base, t.get("path"), "truth.path"), format=_choice(t.get("format", "pair_tsv"), {"pair_tsv", "gaf", "hdf5_matrix"}, "truth.format"), semantics=_choice(t.get("semantics", "direct"), {"direct", "ancestor_closed"}, "truth.semantics"), negative_semantics=_choice(t.get("negative_semantics", "unknown"), {"unknown", "explicit"}, "truth.negative_semantics"), evidence_filter=tuple(str(x) for x in t.get("evidence_filter", [])), unknown_protein_policy=_choice(t.get("unknown_protein_policy", "error"), {"error", "exclude"}, "truth.unknown_protein_policy"), protein_field=str(t.get("protein_field", predictions.protein_field)), term_field=str(t.get("term_field", predictions.term_field)))

    o = _map(raw["ontology"], "ontology")
    unknown += [f"ontology.{x}" for x in _unknown(o, {"path", "format", "release", "relations", "reflexive_closure", "direction", "namespace_roots", "alt_id_policy", "obsolete_policy", "namespace_policy"}, "ontology", strict)]
    relations = tuple(str(x) for x in o.get("relations", ["is_a", "part_of"]))
    if not relations or len(set(relations)) != len(relations) or "all" in relations:
        raise ConfigError("ontology.relations must enumerate unique relation identifiers")
    roots = _map(o.get("namespace_roots", {}), "ontology.namespace_roots")
    ontology = OntologySpec(path=_path(base, o.get("path"), "ontology.path"), format=_choice(o.get("format", "obo"), {"obo"}, "ontology.format"), release=str(o.get("release", "unspecified")), relations=relations, reflexive_closure=bool(o.get("reflexive_closure", True)), direction=_choice(o.get("direction", "child_to_parent"), {"child_to_parent"}, "ontology.direction"), namespace_roots={str(k): str(v) for k, v in roots.items()}, alt_id_policy=_choice(o.get("alt_id_policy", "resolve"), {"resolve", "error", "retain"}, "ontology.alt_id_policy"), obsolete_policy=_choice(o.get("obsolete_policy", "drop"), {"drop", "replaced_by", "error", "retain"}, "ontology.obsolete_policy"), namespace_policy=_choice(o.get("namespace_policy", "close_within_namespace"), {"close_within_namespace", "close_then_filter"}, "ontology.namespace_policy"))
    if not ontology.reflexive_closure:
        raise ConfigError("canonical pipelines require reflexive_closure=true")

    e = _map(raw["evaluation"], "evaluation")
    unknown += [f"evaluation.{x}" for x in _unknown(e, {"prediction_closure", "truth_closure", "root_policy", "term_universe", "explicit_term_file", "universe_label_dependence", "comparison", "threshold_representation", "threshold_grid", "precision_eligibility", "recall_eligibility", "averaging"}, "evaluation", strict)]
    g = _map(e.get("threshold_grid", {}), "evaluation.threshold_grid")
    unknown += [f"evaluation.threshold_grid.{x}" for x in _unknown(g, {"type", "values"}, "evaluation.threshold_grid", strict)]
    values = tuple(float(x) for x in g.get("values", [0.5]))
    if not values or tuple(sorted(set(values))) != values or any(not bounds[0] <= x <= bounds[1] for x in values):
        raise ConfigError("threshold values must be unique, increasing, and in allowed_range")
    evaluation = EvaluationSpec(prediction_closure=_choice(e.get("prediction_closure", "ancestor"), {"none", "ancestor"}, "evaluation.prediction_closure"), truth_closure=_choice(e.get("truth_closure", "ancestor"), {"none", "ancestor"}, "evaluation.truth_closure"), root_policy=_choice(e.get("root_policy", "exclude"), {"include", "exclude"}, "evaluation.root_policy"), term_universe=_choice(e.get("term_universe", "emitted"), {"emitted", "emitted_plus_ancestors", "ontology_namespace", "explicit"}, "evaluation.term_universe"), explicit_term_file=_path(base, e.get("explicit_term_file"), "evaluation.explicit_term_file", True), universe_label_dependence=_choice(e.get("universe_label_dependence", "forbidden"), {"forbidden", "declared_diagnostic"}, "evaluation.universe_label_dependence"), comparison=_choice(e.get("comparison", "greater_equal"), {"greater_equal", "greater"}, "evaluation.comparison"), threshold_representation=_choice(e.get("threshold_representation", "float64_direct"), {"float64_direct", "floor_100_bins", "rounded_decimal"}, "evaluation.threshold_representation"), threshold_grid=ThresholdGridSpec(_choice(g.get("type", "explicit"), {"explicit"}, "evaluation.threshold_grid.type"), values), precision_eligibility=_choice(e.get("precision_eligibility", "predicted_proteins"), {"predicted_proteins", "all_proteins"}, "evaluation.precision_eligibility"), recall_eligibility=_choice(e.get("recall_eligibility", "truth_bearing_proteins"), {"truth_bearing_proteins", "all_proteins"}, "evaluation.recall_eligibility"), averaging=_choice(e.get("averaging", "both"), {"protein_centric", "micro", "both"}, "evaluation.averaging"))
    if evaluation.term_universe == "explicit" and not evaluation.explicit_term_file:
        raise ConfigError("explicit term universe requires explicit_term_file")

    default_ops = {"raw": {"kind": "identity"}, "ancestor_max": {"kind": "ancestor_max", "relations": "contract", "expanded_universe": "contract"}}
    operators = _map(raw.get("operators", default_ops), "operators")
    if operators != default_ops:
        raise ConfigError("MVP registers only frozen raw and ancestor_max operators")

    x = _map(raw.get("external_evaluator", {}), "external_evaluator")
    unknown += [f"external_evaluator.{z}" for z in _unknown(x, {"mode", "path", "version", "input_contract", "pair_output", "count_output", "metric_output", "options"}, "external_evaluator", strict)]
    external = ExternalEvaluatorSpec(mode=_choice(x.get("mode", "none"), {"none", "executable", "python_adapter", "aggregate_file"}, "external_evaluator.mode"), path=str(x["path"]) if x.get("path") is not None else None, version=str(x.get("version", "unspecified")), input_contract=_choice(x.get("input_contract", "raw_scores"), {"raw_scores", "canonical_pairs"}, "external_evaluator.input_contract"), pair_output=_path(base, x.get("pair_output"), "external_evaluator.pair_output", True), count_output=_path(base, x.get("count_output"), "external_evaluator.count_output", True), metric_output=_path(base, x.get("metric_output"), "external_evaluator.metric_output", True), options=dict(_map(x.get("options", {}), "external_evaluator.options")))
    if external.mode == "python_adapter" and (not external.path or ":" not in external.path):
        raise ConfigError("python_adapter path must be module:function")

    q = _map(raw.get("threshold_analysis", {}), "threshold_analysis")
    unknown += [f"threshold_analysis.{z}" for z in _unknown(q, {"enabled", "calibration_split", "target_split", "grouping", "group_file", "policies", "target_score_field", "selection_metric", "tie_break", "bootstrap_draws", "plateau_tolerance_f1", "target_oracle_diagnostic"}, "threshold_analysis", strict)]
    threshold = ThresholdAnalysisSpec(enabled=bool(q.get("enabled", False)), calibration_split=_path(base, q.get("calibration_split"), "threshold_analysis.calibration_split", True), target_split=_path(base, q.get("target_split"), "threshold_analysis.target_split", True), grouping=_choice(q.get("grouping", "protein"), {"cluster_file", "protein"}, "threshold_analysis.grouping"), group_file=_path(base, q.get("group_file"), "threshold_analysis.group_file", True), policies=tuple(str(z) for z in q.get("policies", ["raw_calibrated", "closed_calibrated"])), target_score_field=_choice(q.get("target_score_field", "closed"), {"closed"}, "threshold_analysis.target_score_field"), selection_metric=_choice(q.get("selection_metric", "protein_f1"), {"protein_f1"}, "threshold_analysis.selection_metric"), tie_break=_choice(q.get("tie_break", "lowest_threshold"), {"lowest_threshold"}, "threshold_analysis.tie_break"), bootstrap_draws=int(q.get("bootstrap_draws", 500)), plateau_tolerance_f1=float(q.get("plateau_tolerance_f1", 0.005)), target_oracle_diagnostic=bool(q.get("target_oracle_diagnostic", True)))
    if not threshold.policies or set(threshold.policies) - {"raw_calibrated", "closed_calibrated"} or len(set(threshold.policies)) != len(threshold.policies):
        raise ConfigError("unsupported or duplicate threshold policies")
    if threshold.enabled and (not truth or not threshold.calibration_split or not threshold.target_split):
        raise ConfigError("enabled threshold analysis requires truth and both splits")
    if threshold.grouping == "cluster_file" and not threshold.group_file:
        raise ConfigError("cluster_file grouping requires group_file")
    if threshold.bootstrap_draws < 1 or threshold.plateau_tolerance_f1 < 0:
        raise ConfigError("invalid threshold bootstrap settings")

    deployment = None
    if raw.get("deployment_risk") is not None:
        d = _map(raw["deployment_risk"], "deployment_risk")
        unknown += [f"deployment_risk.{z}" for z in _unknown(d, {"reference_pipeline", "precision_drop_budget", "coverage_drop_budget", "prediction_inflation_budget", "abstention_increase_budget"}, "deployment_risk", strict)]
        try:
            deployment = DeploymentRiskSpec(reference_pipeline=str(d["reference_pipeline"]), precision_drop_budget=float(d["precision_drop_budget"]), coverage_drop_budget=float(d["coverage_drop_budget"]), prediction_inflation_budget=float(d["prediction_inflation_budget"]), abstention_increase_budget=float(d["abstention_increase_budget"]))
        except KeyError as exc:
            raise ConfigError(f"deployment_risk missing {exc.args[0]}") from exc

    return AuditConfig(config_path=source, schema_version=SCHEMA_VERSION, audit_id=audit_id, created_utc=_timestamp(raw["created_utc"]), claim_scope=_choice(raw["claim_scope"], {"evaluation", "deployment", "both"}, "claim_scope"), random_seed=int(raw["random_seed"]), inputs_hash_policy=_choice(raw["inputs_hash_policy"], {"sha256"}, "inputs_hash_policy"), predictions=predictions, truth=truth, ontology=ontology, evaluation=evaluation, operators={key: dict(value) for key, value in operators.items()}, external_evaluator=external, threshold_analysis=threshold, deployment_risk=deployment, unknown_fields=tuple(unknown))
