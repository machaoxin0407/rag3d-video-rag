# Paper Video Retrieval v1 Reproduction Guide

This directory is the byte-stable evaluation replay release for the formal five-mode video retrieval experiment.

It contains the frozen queries, pooled native rankings, adjudicated qrels, supporting scene/evidence manifests, formal results and SHA-256 checksums. It does not redistribute raw videos, generated clips, keyframes or model weights.

Additional audit material:

- `LINEAGE_NOTES.md` explains the byte-distinct but semantically identical dataset-freeze and pool-generation inventory snapshots;
- `review_audit/` retains the exact workbook and reports referenced by the qrels manifest;
- `LARGE_ARTIFACT_LOCATOR.json` records the authorized server paths, sizes, available hashes and known hash-coverage limits for media and indexes.

## Requirements

- Python 3.10 or newer;
- no third-party Python dependency is required for evaluation replay;
- run commands from the repository root.

## One-command validation

Validate payload hashes, dataset/pool/qrels manifest lineage, human-review audit hashes, TREC/CSV consistency, row counts, native run depths and frozen metrics:

```bash
python validate_paper_retrieval_release.py
```

Validate the release and replay the full 10,000-sample paired bootstrap evaluation:

```bash
python validate_paper_retrieval_release.py --replay
```

The replay succeeds only if all three machine-readable result CSV files are byte-identical to the frozen baseline and the evaluation JSON agrees on the metric summary, run depths and paired bootstrap results.

## Direct evaluation

```bash
python evaluate_paper_video_retrieval.py \
  --pool data_video/releases/paper_video_retrieval_v1/manifests/paper_relevance_pool_audit_v1.csv \
  --qrels data_video/releases/paper_video_retrieval_v1/manifests/paper_qrels_v1/paper_video_qrels_graded_v1.csv \
  --qrels-manifest data_video/releases/paper_video_retrieval_v1/manifests/paper_qrels_v1/paper_video_qrels_manifest_v1.json \
  --pool-manifest data_video/releases/paper_video_retrieval_v1/manifests/paper_relevance_pool_run_v1.json \
  --output-dir reports/paper_retrieval_eval_v1_reproduced
```

Expected Tri-Hybrid results at cutoff 10:

| Metric | Value |
|---|---:|
| nDCG@10 | 0.646976 |
| MAP@10 | 0.508945 |
| MRR@10 | 0.722497 |
| Recall@10 | 0.716181 |
| Precision@10 | 0.298667 |

## Evaluation scope

- 100 queries;
- 3,775 judged query-scene pairs;
- 725 unique judged scenes;
- 75 queries with at least one grade-2-or-higher judgment;
- BM25, Dense, Visual, Hybrid and Tri-Hybrid;
- 1,967 frozen results per mode;
- graded nDCG on all 100 queries;
- binary MAP, MRR, Recall and Precision on the 75 binary-evaluable queries;
- 10,000 paired bootstrap samples with seed `20260729`.

Recall and MAP are pool-relative because judgments cover the union of the five native Top-20 runs rather than the entire corpus.

## Byte stability

Files listed in `RELEASE_MANIFEST.json` and `FILE_HASHES.sha256` are frozen payloads. Repository attributes mark release CSV, JSON and TXT payloads as binary so that Git does not change line endings on Windows.

Do not edit a v1 payload in place. Corrections require a new release directory and a versioned change log.

## Large artifacts

Raw video and generated media remain outside Git. Their source or clip hashes and relative paths are retained in the included manifests. Exact server locations and v1 hash-coverage limitations are recorded in `LARGE_ARTIFACT_LOCATOR.json`.

The frozen candidate pool already stores native method ranks and scores for all five modes, so replaying the formal evaluation does not require GPUs, embedding services or the original video files.
