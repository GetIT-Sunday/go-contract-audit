# Public release scope

This repository is deliberately narrower than the private research workspace.
It contains the reusable audit engine, public synthetic fixtures, a small
anonymous diagnosis capsule, and the manuscript sources needed to inspect the
reported method.

The following are excluded:

- raw model weights and large third-party prediction trees;
- restricted or independently licensed annotation and ontology bundles;
- private injected-fault labels, expected diagnosis records, and hidden joins;
- internal experiment logs, review notes, virtual environments, and caches;
- credentials, access tokens, and machine-specific absolute paths.

The capsule's frozen expected answers are part of its documented component
test. They are not labels for a new biological benchmark and must not be
interpreted as independent-team validation.

Before tagging a formal public release, add a license, complete author and
contact metadata, and record the final repository commit in the manuscript's
availability statement. If a DOI is desired, archive the tagged commit with a
service such as Zenodo; GitHub alone does not create a DOI.
