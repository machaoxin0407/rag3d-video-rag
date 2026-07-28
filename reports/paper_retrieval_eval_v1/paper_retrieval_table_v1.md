# Formal video retrieval evaluation

Generated: 2026-07-28T17:44:58.670883+00:00

Primary binary relevance is grade >= 2. Graded nDCG uses
gain $2^{grade}-1$. All rankings are the frozen native Top-20 outputs pooled
across BM25, dense, visual, hybrid, and tri-hybrid. Unjudged scenes outside the
pool are not known relevant; recall and MAP are therefore pool-relative.
Queries without any grade >= 2 judgment are excluded from binary macro metrics.
The summary CSV/JSON also contains `_all_queries` variants that score those
no-positive queries as zero, providing a conservative coverage-adjusted view.

## Main table

| Mode | K | N_bin | nDCG | MAP | MRR | Recall | Precision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | 10 | 75 | 0.469 | 0.299 | 0.547 | 0.484 | 0.188 |
| bm25 | 20 | 75 | 0.506 | 0.324 | 0.555 | 0.632 | 0.124 |
| dense | 10 | 75 | 0.593 | 0.417 | 0.629 | 0.634 | 0.280 |
| dense | 20 | 75 | 0.616 | 0.444 | 0.633 | 0.745 | 0.170 |
| visual | 10 | 75 | 0.588 | 0.400 | 0.594 | 0.652 | 0.261 |
| visual | 20 | 75 | 0.608 | 0.421 | 0.597 | 0.723 | 0.157 |
| hybrid | 10 | 75 | 0.575 | 0.435 | 0.663 | 0.614 | 0.269 |
| hybrid | 20 | 75 | 0.599 | 0.462 | 0.667 | 0.731 | 0.163 |
| tri_hybrid | 10 | 75 | 0.647 | 0.509 | 0.722 | 0.716 | 0.299 |
| tri_hybrid | 20 | 75 | 0.655 | 0.539 | 0.724 | 0.813 | 0.179 |

## Paired bootstrap on nDCG@10

10,000 paired query bootstrap samples, seed 20260729; reference is
tri-hybrid.

| Comparison | Delta | 95% CI | Two-sided p |
| --- | --- | --- | --- |
| bm25 | 0.178 | [0.146, 0.210] | 0.0002 |
| dense | 0.054 | [0.016, 0.093] | 0.0068 |
| visual | 0.059 | [0.022, 0.096] | 0.0016 |
| hybrid | 0.072 | [0.045, 0.099] | 0.0002 |

## nDCG@10 by product class

| Product | Queries | bm25 | dense | visual | hybrid | tri_hybrid |
| --- | --- | --- | --- | --- | --- | --- |
| Air Fryer | 17 | 0.403 | 0.573 | 0.563 | 0.527 | 0.625 |
| Espresso Machine | 17 | 0.569 | 0.684 | 0.671 | 0.689 | 0.772 |
| Pressure Cooker | 17 | 0.439 | 0.553 | 0.602 | 0.557 | 0.623 |
| Printer | 17 | 0.453 | 0.566 | 0.548 | 0.581 | 0.642 |
| Vacuum | 16 | 0.337 | 0.487 | 0.563 | 0.473 | 0.543 |
| Washing Machine | 16 | 0.617 | 0.693 | 0.580 | 0.622 | 0.672 |
