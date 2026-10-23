"""Deterministic signatures of already-observed audit channels."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        return {"__float_hex__": value.hex()}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported signature value {type(value).__name__}")


def _digest(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ObservedSignature:
    """Hash inventory for explicitly available observable channels."""

    channel_digests: tuple[tuple[str, str], ...]
    channel_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {"channel_digests": dict(self.channel_digests), "channel_count": self.channel_count, "digest": self.digest}


def signature_from_channels(channels: Mapping[str, Any]) -> ObservedSignature:
    if not channels:
        raise ValueError("at least one observable channel is required")
    digests = tuple((str(name), _digest(value)) for name, value in sorted(channels.items(), key=lambda item: str(item[0])))
    return ObservedSignature(digests, len(digests), _digest(dict(digests)))

