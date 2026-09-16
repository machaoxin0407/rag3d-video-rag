# P2 执行与 Go/No-Go 报告

生成时间：2026-07-29T09:34:29.858835+00:00

## 结论

当前状态：**P2_CONDITIONAL_NO_GO**。

P2 的可复现实验链路已经建立并实际运行：qrels v2、时间定位、仅开发集
检索消融、一次性来源隔离测试、100 问题端到端评测、受控诊断小集、并发与
故障注入、留一产品类泛化均有机器可读产物。未通过的门槛不会被写成已完成。

阻塞项：retrieval_recall_at_5_target, diagnosis_macro_f1_target, formal_workload_answer_p95_under_15s, 24_hour_soak_complete, human_review_queue_cleared。

## 核心结果

| 项目 | 结果 | 门槛/解释 |
|---|---:|---|
| qrels v2 | 3775 pairs / 0 grade changes | 不覆盖 v1；9 条泄漏风险采用预声明策略 |
| 无强正例问题 | 25 | 归类为候选池缺少直接答案 |
| Tri-Hybrid R@1 IoU=.5 | 0.581 | 目标 ≥0.50 |
| Tri-Hybrid temporal mAP@.5 (all-query) | 0.497 | 74 问宏平均，不可达 proposal 计 0 |
| Tri-Hybrid temporal mAP@.5 (conditional) | 0.541 | 仅 68/74 个可达问，不能作主口径 |
| 开发集 Recall@5 | 0.518 | positive-query-only N=52/60；目标 ≥0.80 |
| 开发集 coverage-adjusted Recall@5 | 0.449 | 无主口径正例问计 0 |
| 一次性 source-disjoint test Recall@5 | 0.632 | positive-query-only N=22/40；未用于选型 |
| 测试集 coverage-adjusted Recall@5 | 0.348 | 无主口径正例问计 0 |
| 端到端问题 | 100 | 100 个唯一 query_id |
| AI judge correctness | 0.596 | AI 评审，失败/高风险待一名人类复核 |
| 证据支持 | 0.502 | AI 评审 |
| 非幻觉 | 0.659 | AI 评审 |
| 媒体有效率 | 1.000 | 鉴权读取实测 |
| 诊断 Macro-F1 | 0.667 | 目标 ≥0.70 |
| 诊断任务失败 | 0 / 18 | 失败按错误预测计入，不从分母删除 |
| 代理诊断任务 P95 | 12.10 s | 场景长度代理片段 |
| 60 秒用户视频时延 | not_measured | 未测量，不宣称达到 30–60 s 目标 |
| 诊断定位 | experimental_only | 受控代理集，不等于真实用户故障集 |
| 检索 P95 | 83.7 ms | 目标 ≤1000 ms |
| 正式 100 问并发工作负载 P95 | 36.62 s | 目标尽量 ≤15 s；未达标 |
| 单用户重复请求 P95 | 9.72 s | 5 次参考测量，不替代正式口径 |
| 冷启动 | not_measured | 正式批次前未单独测量，不以热服务请求冒充 |
| 24 h 稳定性 | not_run | 未完成不得宣称稳定性达标 |

## 方法学边界

- qrels v2 不修改任何相关性等级。`yes` 泄漏项不进入主结果或敏感性结果；
  `uncertain` 不进入主结果但保留在敏感性口径。
- v1 有 75 个 grade>=2 问题；排除一条 `uncertain` 的 grade=2 记录后，
  v2 主口径有 74 个二值可评问题，端到端“无直接视频答案”口径因此为 26 个。
- 权重选择只读取 60 个 development 问题；40 个 source-disjoint test 问题
  在配置冻结后只评一次。
- 检索权重消融基于冻结 Top-20 pool，缺失名次按 21 右删失；它是池内消融，
  不是新的全库召回实验。
- 时间预测区间为检索场景边界，IoU 只与同 scene_id 的人工相关区间比较。
- 诊断集由标准片段、全遮挡和跨产品替换组成，明确标记 synthetic/proxy。
- AI judge 原始输出、输入证据、模型名和提示词版本全部保留。论文正式数字
  仍需一名人类只复核失败项和 safety 项。
- `source_disjoint_test` 是域内来源隔离；留一产品类实验是跨产品代理泛化，
  不冒充 COIN/CrossTask 外部数据集。

## 后续动作

1. 对端到端 `human_review_required=1` 的队列做单人复核并冻结裁决。
2. 若诊断 Macro-F1 未达 0.70，产品 UI 必须继续标为“实验性”，不能作主贡献。
3. 单独安排真实 24 小时窗口运行 `p2_soak_test.py`，结束后释放本项目 GPU。
4. Recall@5 未达 0.80 时，论文如实报告池覆盖限制，不在测试集上继续调权。
