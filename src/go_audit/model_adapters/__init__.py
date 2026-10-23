"""Extensible model-output adapter registry."""

from .base import AdaptRequest, AdaptResult, ModelAdapterError, ModelOutputAdapter
from .registry import AdapterRegistry, builtin_registry, load_plugins
from .runner import run_adapter, validate_canonical

__all__ = [
    "AdaptRequest", "AdaptResult", "ModelAdapterError", "ModelOutputAdapter",
    "AdapterRegistry", "builtin_registry", "load_plugins", "run_adapter", "validate_canonical",
]

