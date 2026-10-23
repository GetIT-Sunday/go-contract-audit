# Data and model access

The public code consumes a canonical continuous-score table or one of the
registered model-output formats. It does not bundle the source model weights,
large prediction matrices, private annotations, or third-party repositories.

To replay a model-format adapter, obtain the model output and its license from
the original project, keep the downloaded files outside this repository, and
declare their paths in a local contract. The adapter records the input hash
and canonical output provenance; it does not receive truth labels, metric
functions, or threshold-selection authority.

The paper's retrospective real-pipeline observations are bounded witnesses,
not a redistribution of the source datasets. Any external rerun must use the
corresponding public release, access terms, and frozen ontology/annotation
snapshot documented by that source.
