# Ecosystem-qualified vulnerability evidence

Jev selected `publish_reference_fix` for actual code and evidence at `e360fd8`. This is a bounded release judgment, not a new rubric score or production approval. The request/response hashes and raw probabilities are retained here.

Independent review reproduced same-name npm/PyPI affected and fixed version collisions: both remain `ecosystem_mismatch` requiring review. Missing ecosystem is rejected on either input side before inference. Python 3.11 verification passed 209 tests across eleven suites and ten CLI replays.

The eight earlier cases and historical live outputs remain unchanged. A separately named migrated fixture retains their original expected outcomes and adds two collision cases. The README documents the input-contract change. Real package-name overlap was checked against package registries; advisory text and versions in regression fixtures are synthetic.

No SBOM ingestion, package-URL parsing, version ranges, vendor-backport interpretation or authoritative registry identity is claimed. Operators must provide agreed normalized names and namespaces. Private registry origin and distribution-specific qualifiers remain outside the matcher. No target-enterprise production acceptance has been established.
