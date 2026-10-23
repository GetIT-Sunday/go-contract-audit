# GO Audit CLI MVP

This package audits GO prediction semantics without importing the current
research project's loaders or evaluators. It accepts long CSV score/truth
tables and a standard OBO file.

```bash
python3 -m go_audit validate go_audit/examples/audit.example.yaml
python3 -m go_audit audit path/to/audit.yaml
```

## Model-output adapters

The audit engine consumes a canonical headered TSV with `protein_id`, `go_id`,
and continuous `score` columns. Built-in adapters translate common model outputs:

```bash
python3 -m go_audit list-adapters

python3 -m go_audit adapt \
  --adapter deepfri-json \
  --input predictions.json \
  --out canonical_predictions/

python3 -m go_audit audit \
  --contract audit.yaml \
  --out audit/
```

Dense matrix adapters default to compressed canonical HDF5 (`scores.h5`) rather
than expanding every cell into a multi-gigabyte text file. Use
`--option canonical_format=long_tsv` only when a text artifact is specifically
needed. The audit reader consumes canonical HDF5 directly.

Adapt and audit in one non-overwriting command:

```bash
python3 -m go_audit adapt-audit \
  --adapter deepfri-json \
  --input predictions.json \
  --contract audit.yaml \
  --out complete_audit/
```

Built-ins include canonical delimited text, generic HDF5 matrices,
InterLabelGO+/SPROF-GO HDF5 aliases, DeepFRI probability JSON, and ProtNote
pandas-HDF logits. Optional dependencies are loaded only by the adapter that
needs them.

### Registering a third-party adapter

A plugin is a local Python module with a single explicit hook:

```python
def register_adapters(registry):
    registry.register("my-model", MyAdapter, origin=__file__)
```

`MyAdapter` declares `name`, `version`, and `description`, and implements
`adapt(request) -> AdaptResult`. A complete template is available at
`go_audit/examples/user_adapter.py`. Load it explicitly:

```bash
python3 -m go_audit list-adapters --plugin ./my_adapter.py
python3 -m go_audit adapt --plugin ./my_adapter.py \
  --adapter my-model --input model_output.json --out canonical_predictions/
```

Plugins execute local Python code and should only be loaded from trusted sources.
The adapter interface does not provide truth, metric, threshold-selection, or
remediation APIs. Trusted plugin source paths and SHA256 hashes are recorded; a
third-party plugin remains ordinary local Python code and is not sandboxed. The output
is rejected unless it passes canonical schema, finite-score, and `[0,1]` checks.
The downstream audit contract still controls duplicate, ontology, and evaluator
semantics.

The semantic audit compares:

- A: thresholded raw scores;
- B: A followed by reflexive ancestor closure;
- C: ancestor-max score propagation followed by the same threshold; and
- D: an optional user-supplied evaluator adapter.

Fixed policies are evaluated exactly as declared. The CLI never searches for a
threshold. Bootstrap draws resample declared clusters or proteins and report
fixed-policy metric uncertainty. JSON, CSV, Markdown, and a SHA256 manifest are
written under `output_dir`. Simulation-specific gates are deliberately kept
outside this portable component until their corresponding public contract is
released.
