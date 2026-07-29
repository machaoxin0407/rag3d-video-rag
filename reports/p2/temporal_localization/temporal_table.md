# P2 temporal localization

Prediction is the native retrieved scene interval. Ground truth is the human relevant sub-interval. Metrics use only primary-eligible grade>=2 judgments and are therefore pool-relative.

| Mode | N | mean IoU | R@1 IoU=.3 | R@1 IoU=.5 | R@1 IoU=.7 | t-mAP .3 | t-mAP .5 | t-mAP .7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 74 | 0.364233 | 0.391892 | 0.364865 | 0.337838 | 0.323731 | 0.321382 | 0.315156 |
| dense | 74 | 0.424987 | 0.445946 | 0.445946 | 0.391892 | 0.416294 | 0.420883 | 0.402664 |
| visual | 74 | 0.409332 | 0.459459 | 0.418919 | 0.391892 | 0.429790 | 0.420714 | 0.431744 |
| hybrid | 74 | 0.488783 | 0.513514 | 0.513514 | 0.472973 | 0.452123 | 0.461418 | 0.452167 |
| tri_hybrid | 74 | 0.546985 | 0.581081 | 0.581081 | 0.554054 | 0.538917 | 0.541091 | 0.555414 |
