"""Portable Gene Ontology prediction audit framework."""

__version__ = "0.4.0"

from .config import AuditConfig, ConfigError, load_config
from .engine import run_audit

__all__ = ["AuditConfig", "ConfigError", "load_config", "run_audit"]
