"""Minimal, deterministic OBO parser for ontology contract audits."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ontology:
    parents: dict[str, frozenset[str]]
    namespaces: dict[str, str]
    obsolete: frozenset[str]
    alt_ids: dict[str, str]
    relation_counts: dict[str, int]
    replacements: dict[str, str]
    considers: dict[str, tuple[str, ...]]

    def canonical(self, term: str) -> str:
        return self.alt_ids.get(term, term)

    def ancestors(self, term: str, reflexive: bool = False) -> frozenset[str]:
        start = self.canonical(term)
        seen = {start} if reflexive else set()
        stack = list(self.parents.get(start, ()))
        while stack:
            parent = stack.pop()
            if parent not in seen:
                seen.add(parent)
                stack.extend(self.parents.get(parent, ()))
        return frozenset(seen)

    def valid_term(self, term: str, namespace: str | None, include_obsolete: bool) -> bool:
        canonical = self.canonical(term)
        return (
            canonical in self.parents
            and (include_obsolete or canonical not in self.obsolete)
            and (namespace is None or self.namespaces.get(canonical) == namespace)
        )


def parse_obo(path: Path, relations: tuple[str, ...]) -> Ontology:
    allowed = set(relations)
    parents: dict[str, set[str]] = defaultdict(set)
    namespaces: dict[str, str] = {}
    obsolete: set[str] = set()
    alt_ids: dict[str, str] = {}
    relation_counts: dict[str, int] = defaultdict(int)
    replacements: dict[str, str] = {}
    considers: dict[str, tuple[str, ...]] = {}
    block: dict[str, list[str]] = {}

    def commit() -> None:
        if "id" not in block:
            return
        term = block["id"][0]
        parents[term]
        if block.get("namespace"):
            namespaces[term] = block["namespace"][0]
        if "true" in block.get("is_obsolete", []):
            obsolete.add(term)
        for alias in block.get("alt_id", []):
            alt_ids[alias] = term
        if block.get("replaced_by"):
            replacements[term] = block["replaced_by"][0].split()[0]
        if block.get("consider"):
            considers[term] = tuple(value.split()[0] for value in block["consider"])
        if "is_a" in allowed:
            for value in block.get("is_a", []):
                parent = value.split()[0]
                parents[term].add(parent)
                relation_counts["is_a"] += 1
        for value in block.get("relationship", []):
            fields = value.split()
            if len(fields) >= 2:
                relation_counts[fields[0]] += 1
                if fields[0] in allowed:
                    parents[term].add(fields[1])

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line == "[Term]":
            commit()
            block = {}
        elif line.startswith("["):
            commit()
            block = {}
        elif ": " in line:
            key, value = line.split(": ", 1)
            block.setdefault(key, []).append(value)
    commit()
    return Ontology(
        parents={key: frozenset(value) for key, value in parents.items()},
        namespaces=namespaces,
        obsolete=frozenset(obsolete),
        alt_ids=alt_ids,
        relation_counts=dict(sorted(relation_counts.items())),
        replacements=replacements,
        considers=considers,
    )


def cycle_nodes(ontology: Ontology) -> list[str]:
    color: dict[str, int] = {}
    cycle: set[str] = set()
    def visit(term: str, trail: tuple[str, ...]) -> None:
        if color.get(term, 0) == 1:
            if term in trail: cycle.update(trail[trail.index(term):])
            return
        if color.get(term, 0) == 2: return
        color[term] = 1
        for parent in sorted(ontology.parents.get(term, ())): visit(parent, trail + (term,))
        color[term] = 2
    for term in sorted(ontology.parents): visit(term, ())
    return sorted(cycle)
