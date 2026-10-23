# Reproducibility guide

There are two public checks with different scopes.

1. The synthetic contract example exercises schema validation, ontology-aware
   closure, fixed thresholds, metrics, and report generation.
2. The diagnosis capsule exercises a production matcher and an independent
   typed reference over three precomputed anonymous observations.

Both checks are deterministic and use fresh output paths. The matcher audit
does not read the frozen expected answers; the separate `check` command reads
them only to compare the audit output with the independent reference.

The public artifacts therefore support component-level reproduction. They do
not regenerate the retrospective model pipelines or establish an independent
team replication of the manuscript's complete experiments.
