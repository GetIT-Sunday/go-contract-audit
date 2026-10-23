"""Protein-centric and micro metrics plus fixed-policy bootstrap."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np


def evaluate(predictions: Iterable[set[str]], truth: Iterable[set[str]], precision_eligibility: str = "predicted", recall_eligibility: str = "truth") -> dict[str, float | int]:
    prediction_list = list(predictions)
    truth_list = list(truth)
    if len(prediction_list) != len(truth_list):
        raise ValueError("prediction/truth length mismatch")
    precisions: list[float] = []
    recalls: list[float] = []
    true_positive = false_positive = false_negative = 0
    predicted_total = 0
    for prediction, gold in zip(prediction_list, truth_list):
        tp = len(prediction & gold)
        fp = len(prediction - gold)
        fn = len(gold - prediction)
        true_positive += tp
        false_positive += fp
        false_negative += fn
        predicted_total += len(prediction)
        if precision_eligibility == "all" or prediction:
            precisions.append(tp / len(prediction) if prediction else 0.0)
        if recall_eligibility == "all" or gold:
            recalls.append(tp / len(gold) if gold else 0.0)
    precision = float(np.mean(precisions)) if precisions else 0.0
    recall = float(np.mean(recalls)) if recalls else 0.0
    micro_precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    micro_recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {
        "protein_precision": precision,
        "protein_recall": recall,
        "protein_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if micro_precision + micro_recall else 0.0,
        "coverage": float(np.mean([bool(value) for value in prediction_list])) if prediction_list else 0.0,
        "predicted_pairs": predicted_total,
        "mean_predicted_terms": predicted_total / len(prediction_list) if prediction_list else 0.0,
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
    }


def fixed_policy_bootstrap(predictions: list[set[str]], truth: list[set[str]], clusters: list[str], draws: int, seed: int, confidence: float, precision_eligibility: str, recall_eligibility: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        grouped[cluster].append(index)
    groups = [grouped[key] for key in sorted(grouped)]
    if not groups:
        raise ValueError("cannot bootstrap an empty cohort")
    rng = np.random.default_rng(seed)
    names = ("protein_precision", "protein_recall", "protein_f1", "micro_precision", "micro_recall", "micro_f1", "coverage", "mean_predicted_terms")
    values = {name: np.empty(draws, dtype=np.float64) for name in names}
    for draw in range(draws):
        selected = rng.integers(0, len(groups), len(groups))
        indices = [index for group in selected for index in groups[group]]
        metric = evaluate([predictions[index] for index in indices], [truth[index] for index in indices], precision_eligibility, recall_eligibility)
        for name in names:
            values[name][draw] = float(metric[name])
    alpha = (1.0 - confidence) / 2.0
    return {name: {"mean": float(array.mean()), "ci_low": float(np.quantile(array, alpha, method="linear")), "ci_high": float(np.quantile(array, 1.0 - alpha, method="linear"))} for name, array in values.items()}


def paired_policy_bootstrap(left: list[set[str]], right: list[set[str]], truth: list[set[str]], clusters: list[str], draws: int, seed: int, confidence: float, precision_eligibility: str, recall_eligibility: str) -> dict[str, dict[str, float]]:
    if not (len(left) == len(right) == len(truth) == len(clusters)):
        raise ValueError("paired bootstrap inputs must have equal length")
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        grouped[cluster].append(index)
    groups = [grouped[key] for key in sorted(grouped)]
    if not groups:
        raise ValueError("cannot bootstrap an empty cohort")
    rng = np.random.default_rng(seed)
    names = ("protein_precision", "protein_recall", "protein_f1", "micro_precision", "micro_recall", "micro_f1", "coverage", "mean_predicted_terms")
    values = {name: np.empty(draws, dtype=np.float64) for name in names}
    for draw in range(draws):
        selected = rng.integers(0, len(groups), len(groups))
        indices = [index for group in selected for index in groups[group]]
        gold = [truth[index] for index in indices]
        left_metric = evaluate([left[index] for index in indices], gold, precision_eligibility, recall_eligibility)
        right_metric = evaluate([right[index] for index in indices], gold, precision_eligibility, recall_eligibility)
        for name in names:
            values[name][draw] = float(left_metric[name]) - float(right_metric[name])
    alpha = (1.0 - confidence) / 2.0
    return {name: {"mean_difference": float(array.mean()), "ci_low": float(np.quantile(array, alpha, method="linear")), "ci_high": float(np.quantile(array, 1.0 - alpha, method="linear"))} for name, array in values.items()}
