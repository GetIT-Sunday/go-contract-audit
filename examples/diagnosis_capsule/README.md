# GO diagnosis component: minimal reproduction capsule

Scope: exact explanation matching over a registered 20-candidate library. Three
retained public examples demonstrate a unique explanation, an equivalence class,
and no matching candidate. This is not an end-to-end ontology evaluator, model
adapter package, or automatic patch executor. It does not establish new accuracy.

Requirements: Python >=3.9, standard library only. No NumPy, GPU, network, or model
weights are needed to run this capsule. Forward candidate surfaces are supplied,
not regenerated here. The two production matcher modules are copied byte-for-byte
from the main project; the separate reference uses typed structural comparisons.

From this directory, with a nonexistent output path:

```sh
python3 audit_examples.py audit --out result.json
python3 audit_examples.py check --out result.json
```

Expected output:

```text
AUDIT 3 cases; expected labels not read
CHECK PASS 3 cases; independent reference and frozen expected sets agree
```

The audit command cannot overwrite an output and does not read expected.json.
Only the check command accesses expected answers and the independent reference.
examples.json uses anonymous IDs; provenance.json records source files and hashes.
All three examples use the same registered candidate library. They are historical
regression examples, not fresh blind validation or independent sampled cases.
For another run, choose a new output filename for both commands.
