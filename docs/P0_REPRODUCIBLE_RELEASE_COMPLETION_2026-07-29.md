# P0 可复现正式发布基线完成记录

> 完成日期：2026-07-29
> 发布 ID：`paper_video_retrieval_v1`
> 来源代码提交：`e94c6bb`
> 对应路线图：[REMAINING_WORK_EXECUTION_ROADMAP_2026-07-29.md](./REMAINING_WORK_EXECUTION_ROADMAP_2026-07-29.md)

## 1. 完成范围

本阶段将此前只完整保留在服务器工作区的正式论文评测输入整理为独立、冻结、可校验的发布包：

```text
data_video/releases/paper_video_retrieval_v1/
```

发布包包含：

- 78 条正式视频的数据集冻结说明；
- 80 条来源和许可登记记录；
- 100 个正式问题；
- 1,263 个场景清单；
- 21,082 条统一证据清单；
- 五种原生模式的 3,775 条联合候选池；
- 每种模式 1,967 条冻结排名；
- 3,775 条正式分级 qrels；
- 五模式正式评测 JSON、CSV 和论文表格；
- 所有冻结文件的字节数和 SHA-256；
- 无第三方依赖的验证及复跑说明。

原始视频、处理后片段、关键帧和模型权重没有放入 Git。发布包保留了相对路径、来源哈希和片段哈希，用于连接服务器大型产物。

服务器原始文件、未跟踪备份和历史结果没有被删除或覆盖。

## 2. 新增产物

```text
data_video/releases/paper_video_retrieval_v1/
├── RELEASE_MANIFEST.json
├── FILE_HASHES.sha256
├── REPRODUCE.md
├── manifests/
│   ├── video_dataset_v1_freeze_20260724.json
│   ├── video_source_inventory.csv
│   ├── paper_video_queries_v1.csv
│   ├── scene_manifest.csv
│   ├── video_evidence_manifest.csv
│   ├── paper_relevance_pool_audit_v1.csv
│   ├── paper_relevance_pool_run_v1.json
│   └── paper_qrels_v1/
└── results/
    └── paper_retrieval_eval_v1/
```

新增验证脚本：

```text
validate_paper_retrieval_release.py
```

## 3. 字节稳定策略

Windows Git 的自动换行转换会改变 CSV/JSON 的 SHA-256。为保证正式输入在 Windows 和 Linux 上保持相同字节，`.gitattributes` 已将发布目录中的 CSV、JSON 和 TXT 标记为 `-text`。

发布包中的 qrels SHA-256 保持为：

```text
463eeef7fabacb09f7b974cc34400e5e92b07afff2a412c76c837dc6d588d412
```

联合候选池 SHA-256：

```text
3faa9117bf0157d5ea00a523754e49c19f19a08f741d1883710fca8459a74421
```

## 4. 验证内容

`validate_paper_retrieval_release.py` 默认检查：

1. 16 个冻结 payload 的文件存在性、字节数和 SHA-256；
2. 视频、场景、证据和问题数量；
3. qrels 和候选池的 3,775 对是否完全一致；
4. 相关性等级分布；
5. 100 个问题和 725 个唯一场景覆盖；
6. 全部 qrels 的人工复核完成状态；
7. 五种模式是否均覆盖 100 个问题；
8. 每种模式是否恰好有 1,967 条原生排名；
9. 每题排名是否连续且深度为 19–20；
10. 冻结 Tri-Hybrid 主结果是否一致。

使用 `--replay` 时，还会：

1. 在临时目录重新执行 10,000 次配对 bootstrap 正式评测；
2. 逐字节比较 summary、per-query 和 breakdown 三个 CSV；
3. 比较 JSON 中的配置、run depth、全部指标和 bootstrap 结果；
4. 自动删除临时复跑目录。

## 5. 验证结果

执行：

```bash
python validate_paper_retrieval_release.py --replay
```

结果：

```text
paper_retrieval_release_check=OK release=paper_video_retrieval_v1 replay=yes
```

三个机器可读结果 CSV 与冻结服务器结果逐字节一致：

| 文件 | SHA-256 |
|---|---|
| `paper_retrieval_metrics_summary_v1.csv` | `2a3ebe90f9c25fc104f7d1254908397e3d87abe84eaa48e1ed6ea375bad5c14c` |
| `paper_retrieval_metrics_per_query_v1.csv` | `adfeb7c5cd4422a451e9a48b960d82dfaf6011855a6ac8578e24603e4ebda762` |
| `paper_retrieval_metrics_breakdown_v1.csv` | `673a87e45cb604cc47f5dce5280462056cb6c263829325b87c84a295288e1d0b` |

Tri-Hybrid @10 复跑结果：

| 指标 | 结果 |
|---|---:|
| nDCG | 0.646976 |
| MAP | 0.508945 |
| MRR | 0.722497 |
| Recall | 0.716181 |
| Precision | 0.298667 |

## 6. 已知例外

当前日常工作目录内存在被 Git 忽略的 `__pycache__`，因此旧的 `validate_delivery.py` 会把工作目录判定为不洁净。检查确认 Git 跟踪文件中不存在 `__pycache__` 或 `.pyc`。

P0 最终验收应以以下三项为准：

- 新鲜 Git checkout 不包含 Python 缓存；
- `validate_paper_retrieval_release.py --replay` 通过；
- 发布目录所有 payload SHA-256 与 `RELEASE_MANIFEST.json` 一致。

不得为了通过检查而删除服务器上的原始产物或用户要求保留的备份。

## 7. P0 验收结论

- [x] 正式评测小型输入进入冻结发布目录；
- [x] qrels、候选池、五模式排名和正式结果完整；
- [x] 大型产物保留策略和哈希记录明确；
- [x] Windows/Linux 字节稳定策略明确；
- [x] 无 GPU、无模型服务即可复跑正式评测；
- [x] 复跑核心 CSV 与冻结结果逐字节一致；
- [x] qrels v1 未被修改；
- [x] 服务器原始文件和备份未被清理。

P0 状态：

```text
COMPLETED — ready for independent acceptance review
```
