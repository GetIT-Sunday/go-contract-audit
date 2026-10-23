"""Explicit registry for built-in and user-supplied model-output adapters."""
from __future__ import annotations

import importlib
import importlib.util
import hashlib
from pathlib import Path
from types import ModuleType
from typing import Callable

from .base import ModelAdapterError, ModelOutputAdapter
from .builtins import CanonicalTSVAdapter, DeepFRIJSONAdapter, HDF5MatrixAdapter, PandasHDFLogitsAdapter

AdapterFactory = Callable[[], ModelOutputAdapter]


class AdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}
        self._origins: dict[str, str] = {}

    def register(self, name: str, factory: AdapterFactory, *, origin: str = "user") -> None:
        normalized = name.strip().lower()
        if not normalized or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in normalized):
            raise ModelAdapterError("adapter names may contain lowercase letters, digits, '-' and '_'")
        if normalized in self._factories:
            raise ModelAdapterError(f"adapter already registered: {normalized}")
        if not callable(factory): raise ModelAdapterError(f"adapter factory is not callable: {normalized}")
        self._factories[normalized] = factory; self._origins[normalized] = origin

    def create(self, name: str) -> ModelOutputAdapter:
        normalized = name.strip().lower()
        if normalized not in self._factories:
            raise ModelAdapterError(f"unknown model adapter {name!r}; run 'goaudit list-adapters'")
        adapter = self._factories[normalized]()
        for field in ("name", "version", "description", "adapt"):
            if not hasattr(adapter, field): raise ModelAdapterError(f"adapter {normalized} lacks {field}")
        if adapter.name != normalized:
            raise ModelAdapterError(f"adapter factory name mismatch: registered={normalized}, object={adapter.name}")
        return adapter

    def describe(self) -> list[dict[str, str]]:
        rows = []
        for name in sorted(self._factories):
            adapter = self.create(name)
            rows.append({"name": name, "version": str(adapter.version), "description": str(adapter.description), "origin": self._origins[name]})
        return rows


def builtin_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register("canonical-tsv", CanonicalTSVAdapter, origin="builtin")
    registry.register("hdf5-matrix", lambda: HDF5MatrixAdapter("hdf5-matrix"), origin="builtin")
    registry.register("interlabelgo-hdf5", lambda: HDF5MatrixAdapter("interlabelgo-hdf5"), origin="builtin")
    registry.register("sprofgo-hdf5", lambda: HDF5MatrixAdapter("sprofgo-hdf5"), origin="builtin")
    registry.register("deepfri-json", DeepFRIJSONAdapter, origin="builtin")
    registry.register("protnote-logits", PandasHDFLogitsAdapter, origin="builtin")
    return registry


def _load_module(reference: str) -> tuple[ModuleType, str]:
    path = Path(reference).expanduser()
    if path.suffix == ".py" or path.exists():
        path = path.resolve()
        if not path.is_file(): raise ModelAdapterError(f"plugin file not found: {path}")
        module_name = "goaudit_user_adapter_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None: raise ModelAdapterError(f"cannot load plugin: {path}")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module, str(path)
    try: return importlib.import_module(reference), reference
    except ImportError as exc: raise ModelAdapterError(f"cannot import plugin {reference}: {exc}") from exc


def load_plugins(registry: AdapterRegistry, references: list[str]) -> list[dict[str, str | None]]:
    origins = []
    for reference in references:
        module, origin = _load_module(reference)
        hook = getattr(module, "register_adapters", None)
        if not callable(hook): raise ModelAdapterError(f"plugin {reference} must define register_adapters(registry)")
        before = {row["name"] for row in registry.describe()}; hook(registry)
        after = {row["name"] for row in registry.describe()}
        if not after - before: raise ModelAdapterError(f"plugin {reference} registered no adapters")
        source = Path(getattr(module, "__file__", ""))
        origins.append({
            "reference": reference, "resolved_source": str(source.resolve()) if source.is_file() else None,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None,
            "registered_names": sorted(after - before),
        })
    return origins
