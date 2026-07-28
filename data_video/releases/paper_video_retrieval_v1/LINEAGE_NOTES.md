# Release Lineage Notes

## Dataset freeze and pool-generation inventory

Two byte-level versions of `video_source_inventory.csv` are intentionally retained:

| Role | Path | SHA-256 |
|---|---|---|
| Dataset freeze input | `manifests/video_source_inventory.csv` | `0c749a48974072ab772f771f6d9819dc9e96528ef18a289aff0abc9beb263643` |
| Pool-generation input | `manifests/pool_generation_inputs/video_source_inventory.csv` | `8add044028c5d5761fc5ec8fce701776db4ae1f660fc78989fe9714711abef3b` |

The first digest is referenced by `video_dataset_v1_freeze_20260724.json`. The second digest is referenced by `paper_relevance_pool_run_v1.json`.

A column-by-column CSV comparison confirms that both files contain the same 80 records and that every parsed cell is identical. Their SHA-256 values differ only because the dataset-freeze copy uses CRLF record separators and the pool-generation copy uses LF record separators.

The release validator checks:

1. both byte-level hashes;
2. complete parsed CSV equality;
3. 78 accepted formal records;
4. six formal classes with 13 records each;
5. the pool manifest against the LF pool-generation input.

Neither historical manifest is rewritten, so both the dataset-freeze and pool-generation provenance remain truthful.

## Evaluation replay boundary

The formal evaluation replay starts from the frozen union pool. It reconstructs the five native runs from `method_ranks_json`, evaluates them against frozen qrels and repeats the paired bootstrap.

Embedding indexes are not required for this replay. Their server paths, byte sizes and hashes are preserved in `LARGE_ARTIFACT_LOCATOR.json`, and their hashes are also recorded by the historical pool manifest.

Regenerating the candidate pool from models is a separate, heavier experiment that requires the original embedding services and model revisions. It is not claimed by this evaluation replay release.

## Human-review evidence

The exact final workbook and the two reports referenced by the qrels manifest are retained under `review_audit/`. Their SHA-256 values are validated against `paper_video_qrels_manifest_v1.json`.

The workbook is retained in the private repository for research audit. Any public release must assess licensing, privacy and reviewer pseudonymization before publishing it.
