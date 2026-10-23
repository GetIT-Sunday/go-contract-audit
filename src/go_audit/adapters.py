"""Opt-in adapter boundary for project-specific evaluator implementations."""
from __future__ import annotations

import importlib
from typing import Any, Callable

from .config import ExternalEvaluatorSpec


class AdapterError(RuntimeError):
    pass


def load_adapter(spec: ExternalEvaluatorSpec) -> Callable[..., Any]:
    if not spec.path:
        raise AdapterError("python adapter path is missing")
    module_name, function_name = spec.path.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
    except (ImportError, AttributeError) as exc:
        raise AdapterError(f"cannot load adapter {spec.path}: {exc}") from exc
    if not callable(function):
        raise AdapterError(f"adapter {spec.path} is not callable")
    return function


def call_adapter(spec: ExternalEvaluatorSpec, *, proteins, terms, scores, thresholds, contract) -> dict[str, Any]:
    result = load_adapter(spec)(
        proteins=proteins,
        terms=terms,
        scores=scores,
        thresholds=thresholds,
        contract=contract,
        options=dict(spec.options),
    )
    if not isinstance(result, dict) or "predictions" not in result:
        raise AdapterError("adapter must return {'predictions': {threshold: [sets]}}")
    return result
