# P2 temporal localization

Prediction is the native retrieved scene interval. Ground truth is the human relevant sub-interval. Metrics use only primary-eligible grade>=2 judgments and are therefore pool-relative.

Conditional t-mAP excludes queries for which no frozen scene proposal can reach the threshold; all-query t-mAP scores those queries as zero.

| Mode | N | mean IoU | R@1 IoU=.3 | R@1 IoU=.5 | R@1 IoU=.7 | t-mAP(all) .3 | t-mAP(all) .5 | t-mAP(all) .7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 74 | 0.364233 | 0.391892 | 0.364865 | 0.337838 | 0.310606 | 0.295324 | 0.272567 |
| dense | 74 | 0.424987 | 0.445946 | 0.445946 | 0.391892 | 0.399417 | 0.386758 | 0.348250 |
| visual | 74 | 0.409332 | 0.459459 | 0.418919 | 0.391892 | 0.412366 | 0.386602 | 0.373400 |
| hybrid | 74 | 0.488783 | 0.513514 | 0.513514 | 0.472973 | 0.433794 | 0.424006 | 0.391063 |
| tri_hybrid | 74 | 0.546985 | 0.581081 | 0.581081 | 0.554054 | 0.517069 | 0.497219 | 0.480358 |
