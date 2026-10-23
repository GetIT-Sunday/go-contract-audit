# GO Evaluation Contract Audit

An executable, evidence-aware framework for auditing Gene Ontology prediction
evaluation contracts. It makes score stages, ontology policies, hierarchy
operators, term universes, eligibility rules, thresholds, and evaluator
semantics explicit before comparing outputs.

The audit is intentionally bounded. It replays a registered candidate family
against the observation channels that are actually available, returns exact or
subset-minimal explanations when they are identifiable, and reports
equivalence or abstention when the evidence cannot support a unique cause. It
does not infer hidden faults, claim universal evaluator correctness, or act as
an automatic patch executor.

## Repository layout

- `src/go_audit/`: portable audit engine and model-output adapter registry.
- `examples/`: a small synthetic contract and an anonymous three-case matcher
  capsule. No model weights or restricted biological datasets are included.
- `paper/`: manuscript source, references, five vector figures, and the
  supplementary methods.
- `docs/`: release scope, data-access limits, and reproducibility notes.
- `scripts/`: deterministic smoke checks for the public artifacts.

## Quick start

Python 3.9 or newer is required. The core engine uses NumPy and PyYAML; HDF5
adapters additionally use `h5py`.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
python3 -m go_audit list-adapters
python3 -m go_audit validate --contract examples/audit.example.yaml --out /tmp/goaudit-validation
python3 scripts/verify_release.py
```

The contract paths in `examples/audit.example.yaml` are relative to the
`examples/` directory. Run the command from that directory, or provide a
contract with paths resolved for your own data.

## Reproduce the diagnosis capsule

The capsule is a component-level reproduction over three precomputed,
anonymous observations. It exercises exact matching, minimal explanations,
equivalence, and unresolved cases. It does not regenerate ontology surfaces,
run a model, or establish an independent biological validation.

```bash
cd examples/diagnosis_capsule
python3 audit_examples.py audit --out /tmp/goaudit-capsule-result.json
python3 audit_examples.py check --out /tmp/goaudit-capsule-result.json
```

Expected output is `AUDIT 3 cases` followed by `CHECK PASS 3 cases`.

## Data and model availability

The repository does not redistribute third-party model weights, large model
outputs, restricted annotations, or the original DeepFRI/InterLabelGO+/SPROF-GO
data trees. See `docs/data_access.md` for the access boundary and the steps
needed to replay a public model-format adapter with data obtained from its
original source.

## Status and citation

This repository is the public artifact staging area for the accompanying
manuscript. The manuscript reports bounded controlled and retrospective audits;
its claims should be read together with the stated observation and data-access
limits. A software or paper license and author metadata must be added before a
formal public release. See `docs/release_scope.md`.
