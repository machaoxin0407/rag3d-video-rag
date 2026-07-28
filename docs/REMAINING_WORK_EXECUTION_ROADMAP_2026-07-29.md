# Video RAG 剩余工作执行路线图

> 文档版本：v1.0
> 基线日期：2026-07-29
> 执行周期建议：4–6 周
> 总体原则：产品可部署优先，论文实验与产品研发共享同一套冻结数据和代码
> 上位计划：[VIDEO_RAG_MASTER_PLAN.md](./VIDEO_RAG_MASTER_PLAN.md)
> 正式检索结果：[PAPER_VIDEO_RETRIEVAL_EVALUATION_2026-07-29.md](./PAPER_VIDEO_RETRIEVAL_EVALUATION_2026-07-29.md)

## 1. 文档目的

本文档用于指导 Video RAG 项目的剩余开发、评测、部署和 SCI 投稿工作。后续工作应以本文档的任务顺序、验收标准和产物路径为准。

当前阶段不是从零开始。以下部分已经完成，不应重复标注或重新调整冻结结果：

- 78 条正式论文视频，覆盖 6 类产品；
- 1,263 个视频场景；
- ASR、OCR、VLM、Dense 和 Visual 索引流水线；
- 100 个正式问题；
- 3,775 个问题—场景相关性判断；
- 每行至少两名独立人类复核员实际看片；
- 146 个争议行由第三名人类仲裁；
- qrels v1 已冻结；
- BM25、Dense、Visual、Hybrid、Tri-Hybrid 五种模式正式评测；
- nDCG、MAP、MRR、Recall、Precision、分组结果和配对 bootstrap；
- `/chat` 基础接口可并列返回文字答案、手册图片标记和视频片段。

当前正式 qrels SHA-256：

```text
463eeef7fabacb09f7b974cc34400e5e92b07afff2a412c76c837dc6d588d412
```

除非发现可证明的标注错误，不允许直接覆盖 qrels v1。任何修订必须生成 `paper_qrels_v2`，同时保留 v1 和变更日志。

## 2. 当前结论

当前项目已经完成“视频检索研究原型和论文核心检索实验”，但还没有完成以下最初目标：

1. 可由干净代码仓库复现的正式发布包；
2. 真正使用手册、图片和视频证据联合生成答案；
3. 用户上传视频的步骤识别与偏差诊断；
4. 生产环境部署、监控、并发和安全验收；
5. 时间定位、端到端答案质量和外部泛化实验；
6. 完整 SCI 英文论文及投稿材料。

执行优先级固定为：

```text
P0 可复现性冻结
  -> P1 可部署产品闭环
  -> P2 产品与论文正式评测
  -> P3 论文写作与投稿
```

P0 未通过前，不开始修改正式检索算法。P1 未形成可运行闭环前，不将论文主张扩大为“可部署端到端系统”。

## 3. 完成定义

项目只有同时满足以下条件，才能标记为“达到最初预期”：

### 3.1 产品完成定义

- 一个统一入口接收文字问题，并返回：
  - 基于证据的文字答案；
  - 可访问的手册图片；
  - 带开始和结束时间的视频片段；
  - 答案句子与证据之间的引用关系；
- 一个用户视频入口支持 60 秒以内视频：
  - 异步上传；
  - 任务状态查询；
  - 产品和步骤识别；
  - 操作偏差或无法判断结果；
  - 下一步建议和置信度；
- 服务可通过固定部署方式启动、停止和重启；
- 服务具备鉴权、路径安全、大小限制、超时、错误降级和日志；
- 完成离线测试、在线 smoke、并发和 P95 延迟测试；
- 服务器任务完成后释放本项目占用的 GPU 服务和显存。

### 3.2 论文完成定义

- 冻结数据、qrels、运行文件和评测脚本可复现；
- Tri-Hybrid 至少在两个核心指标上显著优于最强可复现基线；
- 完成时间定位指标；
- 完成端到端答案和引用质量指标；
- 完成至少一个外部数据集或跨产品泛化实验；
- 完成消融、失败案例、效率和局限性分析；
- 完成英文论文、图表、参考文献、补充材料和投稿信；
- 所有数字可追溯到冻结 CSV/JSON，不允许手工修改论文表格中的实验数字。

## 4. P0：建立可复现的正式发布基线

> 状态：已完成，验收证据见
> [P0_REPRODUCIBLE_RELEASE_COMPLETION_2026-07-29.md](./P0_REPRODUCIBLE_RELEASE_COMPLETION_2026-07-29.md)。

### 4.1 当前问题

服务器 `~/rag3d-video` 的 Git 提交已同步到 `e94c6bb`，但服务器仍存在以下未提交或未跟踪的正式产物：

- 完整 ASR、OCR、VLM、scene 和 evidence manifest；
- 正式候选池及运行审计；
- AI 预标注和运行记录；
- 服务器生成结果备份。

本地 Git 版本的 `scene_manifest.csv` 只有 256 个场景，而服务器正式实验使用 1,263 个场景。因此，当前评测结果虽然已经生成，但还不能从干净 clone 完整复现。

### 4.2 执行任务

- [x] 对服务器当前状态执行只读盘点，不删除任何已有文件；
- [x] 建立 `data_video/releases/paper_video_retrieval_v1/` 发布目录；
- [x] 将复现必需的小型 manifest、候选池、运行文件和哈希清单纳入版本管理；
- [x] 原始视频、关键帧、大型中间文件继续保留在 Git 之外；
- [x] 为大型产物建立对象存储或服务器固定路径清单；
- [x] 每个冻结文件记录相对路径、字节数和 SHA-256；
- [x] 明确评测复跑只依赖 Python 3.10+ 标准库；
- [x] 从独立临时目录完成一次完整评测复跑；
- [x] 比较新旧评测 JSON 和 CSV，核心指标完全一致；
- [x] 发布包不包含 `__pycache__`，服务器备份保持不变。

建议发布目录：

```text
data_video/releases/paper_video_retrieval_v1/
├── RELEASE_MANIFEST.json
├── FILE_HASHES.sha256
├── REPRODUCE.md
├── manifests/
│   ├── video_dataset_v1_freeze_20260724.json
│   ├── paper_video_queries_v1.csv
│   ├── scene_manifest.csv
│   ├── video_evidence_manifest.csv
│   ├── paper_relevance_pool_audit_v1.csv
│   ├── paper_relevance_pool_run_v1.json
│   └── paper_qrels_v1/
├── runs/
│   ├── bm25.csv
│   ├── dense.csv
│   ├── visual.csv
│   ├── hybrid.csv
│   └── tri_hybrid.csv
└── results/
    └── paper_retrieval_eval_v1/
```

### 4.3 复现命令模板

以下命令应在 `REPRODUCE.md` 中替换为最终固定路径：

```bash
cd ~/rag3d-video
source .venv/bin/activate

python evaluate_paper_video_retrieval.py \
  --pool data_video/releases/paper_video_retrieval_v1/manifests/paper_relevance_pool_audit_v1.csv \
  --qrels data_video/releases/paper_video_retrieval_v1/manifests/paper_qrels_v1/paper_video_qrels_graded_v1.csv \
  --qrels-manifest data_video/releases/paper_video_retrieval_v1/manifests/paper_qrels_v1/paper_video_qrels_manifest_v1.json \
  --pool-manifest data_video/releases/paper_video_retrieval_v1/manifests/paper_relevance_pool_run_v1.json \
  --output-dir reports/paper_retrieval_eval_v1_reproduced
```

### 4.4 P0 验收门槛

- [x] 干净 clone 不依赖服务器脏工作区即可获得全部小型正式输入；
- [x] 100 个问题、3,775 个判断和五种模式均通过完整性检查；
- [x] qrels SHA-256 与冻结值一致；
- [x] 复跑后的 nDCG、MAP、MRR、Recall 和 Precision 与 v1 完全一致；
- [x] 正式输入和结果均进入解释明确的冻结发布目录；
- [x] `validate_delivery.py` 的本地缓存例外已有书面说明；
- [x] 发布说明明确哪些文件不进入 Git、保存位置以及哈希验证方法。

P0 预计耗时：2–3 个工作日。

## 5. P1：完成可部署的三模态产品闭环

### 5.1 将正式最优检索模式接入产品

当前 `/chat` 默认请求 Hybrid；当 Dense 服务不可用时会降级到 BM25。正式实验最优模式是 Tri-Hybrid，但服务器的 Dense 和 Visual 服务当前没有运行。

执行任务：

- [ ] 在配置中明确区分 `development`、`evaluation` 和 `production` 模式；
- [ ] 生产配置显式使用 `tri_hybrid`；
- [ ] 启动 Dense 和 Visual embedding 查询服务；
- [ ] 健康检查返回请求模式、实际模式和是否发生降级；
- [ ] API 响应或内部 trace 保存 `requested_mode` 与 `effective_mode`；
- [ ] 禁止评测时发生无提示的 BM25 回退；
- [ ] 服务停止后确认两张 GPU 恢复空闲状态。

建议增加的健康状态：

```json
{
  "status": "ok",
  "retrieval": {
    "requested_mode": "tri_hybrid",
    "dense_service": "ready",
    "visual_service": "ready",
    "fallback": false
  }
}
```

验收：

- [ ] 100 个正式问题在线运行时均为真实 Tri-Hybrid；
- [ ] 与冻结离线 Top-K 的一致率得到记录；
- [ ] Dense 或 Visual 故障时能降级，但日志和响应 trace 可识别。

### 5.2 让视频证据参与答案生成

当前实现先生成手册答案，再单独检索视频。下一版必须先检索多模态证据，再生成最终答案。

目标流程：

```text
用户问题
  -> 产品与意图路由
  -> 手册段落/图片检索
  -> 视频场景 Tri-Hybrid 检索
  -> 证据去重、冲突检查和排序
  -> 基于证据生成答案
  -> 引用校验
  -> 文字 + 手册图片 + 视频片段
```

执行任务：

- [ ] 将视频证据放入回答模型上下文；
- [ ] 每条证据分配稳定 `evidence_id`；
- [ ] 回答句子引用手册段落、手册图片或视频场景；
- [ ] 视频与手册冲突时优先采用安全的手册说明并提示差异；
- [ ] 没有可靠视频时只返回手册答案，不强行添加视频；
- [ ] 高风险问题设置安全模板和低置信度降级；
- [ ] 防止模型生成不存在的图片、视频或时间戳。

建议 `/v2/chat` 响应：

```json
{
  "answer": "……",
  "citations": [
    {
      "citation_id": "C1",
      "type": "manual_section",
      "evidence_id": "manual-...",
      "supports": ["sentence-1"]
    },
    {
      "citation_id": "C2",
      "type": "video_scene",
      "evidence_id": "espresso-040-scene-0003",
      "start_seconds": 18.2,
      "end_seconds": 31.6,
      "supports": ["sentence-2"]
    }
  ],
  "manual_images": [],
  "videos": []
}
```

验收：

- [ ] 答案中的关键操作步骤至少有一项真实证据支持；
- [ ] 所有返回媒体路径均存在且通过鉴权可访问；
- [ ] 不相关视频不因固定返回数量而进入结果；
- [ ] 证据不足时明确回答“不确定”或请求用户补充信息。

### 5.3 完成结构化手册图片输出

当前手册图片主要通过答案中的 `<PIC>` 标记返回。产品版需要结构化字段，便于前端稳定渲染。

执行任务：

- [ ] 增加 `manual_images` 数组；
- [ ] 返回图片 ID、手册 ID、页码或章节、URL、caption；
- [ ] 图片 URL 使用鉴权媒体端点；
- [ ] 保留 `<PIC>` 兼容逻辑，但前端优先读取结构化字段；
- [ ] 防止目录穿越和未授权原始文件访问。

验收：

- [ ] 100 个端到端问题中的每个返回图片都真实存在；
- [ ] 图片与引用章节一致；
- [ ] 图片有效率达到 100%。

### 5.4 实现用户视频诊断 MVP

这是最初目标中目前完全缺失的主要模块。

建议接口：

```text
POST /v2/video-jobs
GET  /v2/video-jobs/{job_id}
GET  /v2/video-jobs/{job_id}/result
DELETE /v2/video-jobs/{job_id}
```

首版限制：

- 视频最长 60 秒；
- MP4/MOV/WebM 白名单；
- 限制文件大小和分辨率；
- 上传文件进入项目隔离临时目录；
- 分析完成或超时后按策略删除临时副本；
- 不允许上传文件名决定服务器路径。

诊断流程：

```text
上传视频
  -> 格式、安全和大小检查
  -> 抽帧/镜头切分/ASR/OCR
  -> 产品、部件、动作和状态识别
  -> 与标准视频和手册步骤对齐
  -> 识别当前步骤
  -> 判断正常、偏差、高风险或无法判断
  -> 返回下一步建议和证据
```

最小诊断标签：

```text
correct_step
wrong_order
missing_step
wrong_component
unsafe_action
device_state_mismatch
insufficient_evidence
out_of_scope
```

由于当前没有可录制实物，第一版先采用：

1. 正式视频中的标准片段作为正常样例；
2. 通过截断、乱序、遮挡和缺帧形成受控偏差样例；
3. 将合成偏差明确标记为 synthetic，不冒充真实用户故障；
4. 后续再补充真实用户视频或委托录制 OOD 集。

验收：

- [ ] 视频任务创建、查询和结果返回完整；
- [ ] 任务失败不会影响普通 `/chat`；
- [ ] 60 秒视频在目标硬件上完成耗时得到记录；
- [ ] 低置信度和高风险情况触发安全降级；
- [ ] 至少建立一个可评测的诊断小集；
- [ ] Macro-F1 达到 70%，否则产品只能标记为实验性功能。

### 5.5 前端演示和播放器

执行任务：

- [ ] 建立最小 Web 演示界面；
- [ ] 支持文字问题、图片输入和用户视频上传；
- [ ] 手册图片可放大；
- [ ] 视频按 `start_seconds` 自动定位；
- [ ] 显示分析中、成功、失败和降级状态；
- [ ] 不在页面暴露服务器绝对路径、Token 或内部错误堆栈。

验收：

- [ ] 非开发人员可按照 README 独立完成一次查询；
- [ ] 六类产品各完成至少一个成功演示；
- [ ] 视频时间定位可在主流浏览器正常工作。

### 5.6 生产部署

需要补充：

```text
Dockerfile
compose.yaml
compose.server.yaml
.env.example
healthcheck
start/stop/status scripts
deployment runbook
```

部署要求：

- API、Dense、Visual 和异步 Worker 分离；
- 模型服务只绑定本机或受控网络；
- 外部访问使用反向代理和 TLS；
- Token、API Key 和服务器地址只存在服务器 `.env`；
- GPU0/GPU1 分工固定并记录；
- 日志不保存原始用户视频或 Base64 内容；
- 提供资源释放命令。

P1 预计耗时：10–15 个工作日。

## 6. P2：补齐产品与论文正式评测

### 6.1 修订评测协议但不覆盖 qrels v1

执行任务：

- [ ] 对 2 条 `source_leakage=yes` 和 7 条 `uncertain` 再裁决；
- [ ] 明确论文主结果是否排除泄漏项；
- [ ] 对 25 个没有等级 ≥2 正例的问题分类：
  - 数据库确实无答案；
  - 候选池未召回；
  - 问题不可回答；
  - 标注阈值过严；
- [ ] 不得为了提升分数直接修改相关性等级；
- [ ] 如需更改，发布 qrels v2 和逐行变更原因。

### 6.2 时间定位评测

当前 394 个等级 ≥2 的判断已经具有相关时间边界，应直接利用现有标注计算：

- R@1, IoU=0.3；
- R@1, IoU=0.5；
- R@1, IoU=0.7；
- mean IoU；
- temporal mAP@0.3/0.5/0.7；
- 按产品和问题类型分组的时间定位结果。

验收目标：

- [ ] R@1, IoU=0.5 达到或接近 50%；
- [ ] 所有指标脚本化生成；
- [ ] 论文表格从 CSV 自动导出。

### 6.3 检索优化

正式 Tri-Hybrid Recall@5 为 0.571，低于原目标 0.800。优化只能使用 development 数据，不得在 source-disjoint test 上调权重。

优先实验：

- [ ] 查询类型自适应融合权重；
- [ ] 产品类别过滤或软路由；
- [ ] Cross-encoder/VLM rerank；
- [ ] 场景相邻窗口合并；
- [ ] ASR、OCR、VLM 字段权重消融；
- [ ] 中英文查询归一化；
- [ ] 对无等级 ≥2 正例问题单独分析。

必须保存：

- 实验 ID；
- 代码提交 SHA；
- 配置；
- 使用的数据 split；
- 随机种子；
- 指标；
- 是否查看过测试结果。

停止条件：

- 达到 Recall@5 ≥0.80；或
- 连续三组合理实验无显著提升，正式调整产品目标并记录原因；或
- 提升以明显损害 nDCG/MRR、延迟或稳定性为代价。

### 6.4 端到端答案与引用评测

建立至少 100 个问题的端到端评测集，至少包含：

- 答案正确性；
- 手册证据支持率；
- 视频证据支持率；
- 图片有效率；
- 视频时间链接有效率；
- 幻觉率；
- 安全降级正确率；
- 无答案问题拒答正确率。

建议评测方式：

1. 规则检查媒体路径、引用 ID 和时间边界；
2. AI 评审答案与证据一致性；
3. 一名人类复核 AI 评审中的失败项和高风险项；
4. 保存模型、提示词、输入证据和原始评分。

### 6.5 性能与稳定性

正式测试至少包含：

- 冷启动和预热后延迟；
- 单用户与并发 2/4/8；
- P50、P95、P99；
- API 完整回答耗时；
- 检索耗时；
- 用户视频任务耗时；
- GPU 显存；
- CPU 和内存；
- 24 小时稳定性；
- Dense/Visual/LLM 故障注入与降级。

原目标：

- 知识库检索 P95 ≤5 秒；
- 完整回答 P95 尽量 ≤15 秒；
- 60 秒用户视频尽量在 30–60 秒完成。

当前 29–78 ms 的检索延迟只能作为单进程工程基线，不能代替正式并发测试。

### 6.6 外部或泛化实验

论文 Go/No-Go 要求至少完成一次外部数据集或跨产品泛化验证。`source_disjoint_test` 是必要的来源隔离，但不能完全替代这一项。

推荐顺序：

1. 留一产品类别测试：五类建立配置，一类只用于最终测试；
2. 使用 COIN/CrossTask 中可对应的操作任务做外部检索；
3. 若外部任务不匹配，则增加未参与开发的新产品类别；
4. 明确区分领域内来源隔离和跨领域泛化。

P2 预计耗时：7–10 个工作日，可与 P1 后半段并行。

## 7. P3：SCI 论文写作与投稿

### 7.1 推荐论文定位

在当前证据下，建议采用以下稳健定位：

> 面向产品技术支持的手册—图片—视频场景多模态检索系统，以及带有人类复核分级相关性判断的领域评测基准。

在用户视频诊断和时间定位实验完成前，不应把“操作偏差诊断”写成已经验证的主要贡献。

建议核心贡献：

1. 面向产品支持的文本、手册图片和视频场景联合证据框架；
2. 结合 BM25、Dense 和 Visual 的 Tri-Hybrid 检索方法；
3. 具有双人独立复核和三方仲裁的分级视频相关性基准；
4. 来源隔离评测、显著性检验和可解释失败分析；
5. 经部署和效率测试的实际系统。

### 7.2 论文结构

```text
1. Abstract
2. Introduction
3. Related Work
4. Task Definition
5. Dataset and Annotation Protocol
6. Method
   6.1 Manual and Video Evidence Construction
   6.2 Text/Dense/Visual Retrieval
   6.3 Tri-Hybrid Fusion
   6.4 Evidence-grounded Answer Generation
   6.5 Optional User-video Diagnosis
7. Experiments
   7.1 Research Questions
   7.2 Baselines and Metrics
   7.3 Main Retrieval Results
   7.4 Temporal Localization
   7.5 Ablation
   7.6 Generalization
   7.7 Efficiency
   7.8 End-to-end Answer Quality
8. Error Analysis and Discussion
9. Ethics, Licensing and Limitations
10. Conclusion
```

### 7.3 必须生成的论文图表

- [ ] 系统总架构图；
- [ ] 数据采集、AI 预标注和人类复核流程图；
- [ ] 六类产品和数据 split 统计表；
- [ ] 五模式主结果表；
- [ ] 配对 bootstrap 表；
- [ ] 分产品结果图；
- [ ] 时间定位结果表；
- [ ] 消融表；
- [ ] 泛化结果表；
- [ ] 延迟和显存表；
- [ ] 成功与失败案例图；
- [ ] 端到端回答与引用示例。

### 7.4 论文数字管理

新增统一目录：

```text
paper/
├── manuscript/
├── figures/
├── tables/
├── bibliography/
├── supplementary/
└── artifacts_manifest.json
```

规则：

- 表格由脚本读取冻结 CSV/JSON 生成；
- 图表记录生成脚本、输入哈希和提交 SHA；
- 文中所有主要指标保留机器可读来源；
- 不允许复制粘贴后手工改变小数；
- 主结果必须同时披露 pool-relative、75 个二值可评测问题和 100 问题 coverage-adjusted 口径；
- 必须披露 25 个无等级 ≥2 正例问题和候选池未穷尽判断的限制。

### 7.5 投稿前检查

- [ ] 完整英文初稿；
- [ ] 共同作者审阅；
- [ ] 图表编号和引用一致；
- [ ] 最新相关工作检索完成；
- [ ] 期刊 SCI 收录、分区、主题范围、版面费和数据政策重新核验；
- [ ] 查重和语言检查；
- [ ] 数据与代码发布范围符合授权条件；
- [ ] Cover Letter；
- [ ] Highlights；
- [ ] Author Contributions；
- [ ] Data Availability；
- [ ] Ethics and Licensing；
- [ ] Supplementary Material；
- [ ] 最终 PDF 视觉检查；
- [ ] 投稿系统字段与论文一致。

P3 预计耗时：10–15 个工作日，可在 P2 主结果稳定后开始。

## 8. 六周执行安排

| 周次 | 主要目标 | 必须交付 |
|---|---|---|
| 第 1 周 | P0 可复现冻结；部署骨架 | release manifest、完整候选池与运行文件、干净复跑结果、部署配置骨架 |
| 第 2 周 | Tri-Hybrid 产品接入；证据联合回答 | `/v2/chat`、结构化图片和引用、真实模式/降级 trace |
| 第 3 周 | 用户视频诊断 MVP；前端播放器 | video-jobs API、诊断小集、演示页面 |
| 第 4 周 | 时间定位、端到端答案、性能测试 | IoU/mAP、答案与引用评测、P50/P95/P99 |
| 第 5 周 | 检索优化、泛化、消融、失败分析 | 新主结果、外部/跨产品结果、论文全部图表 |
| 第 6 周 | 英文论文定稿与投稿准备 | 完整稿、补充材料、复现包、投稿清单 |

如果产品实现或诊断数据耗时超过预期，应优先保证：

1. 可复现性；
2. 联合证据回答；
3. 部署与端到端评测；
4. 正式检索论文；
5. 将用户视频诊断降为后续工作。

不得为了赶论文而声称未完成的诊断功能已经验证。

## 9. 每日和每周管理方式

### 9.1 每日记录

每天更新工作日志：

```text
日期：
代码提交：
数据版本：
完成任务：
运行实验：
主要结果：
失败与原因：
服务器服务：
GPU 是否释放：
下一步：
```

### 9.2 实验登记

每个实验必须有唯一 ID，例如：

```text
RET-20260730-001
TEMP-20260801-001
ANS-20260805-001
DIAG-20260807-001
```

每个实验至少保存：

```json
{
  "experiment_id": "RET-20260730-001",
  "git_commit": "...",
  "dataset_release": "paper_video_retrieval_v1",
  "qrels_sha256": "...",
  "config": {},
  "seed": 20260730,
  "started_at": "...",
  "finished_at": "...",
  "status": "completed",
  "output_paths": []
}
```

### 9.3 每周 Go/No-Go

每周结束只回答四个问题：

1. 本周交付物是否可由另一台机器复现？
2. 是否有未记录的数据、阈值或测试集变化？
3. 产品是否比上周更接近真实用户可用？
4. 当前论文主张是否被实验结果充分支持？

任一答案为“否”时，下一周优先修复，不继续扩大功能范围。

## 10. 禁止事项

- 不覆盖 qrels v1；
- 不在测试集上选择融合权重；
- 不把 Hit@5 当作 Recall@5；
- 不把 source-disjoint 直接写成外部数据集；
- 不把检索到视频写成答案使用了视频证据；
- 不把 AI 预标注写成人工独立标注；
- 不声称用户视频诊断已经实现或达到 Macro-F1；
- 不提交原始视频、私钥、Token、API Key 或服务器 `.env`；
- 不清理服务器原始产物、备份或其他工程文件；
- 不结束其他用户或其他工程的 GPU/CPU 进程；
- 不在服务结束后遗留本项目 GPU 模型；
- 不手工修改正式结果表中的实验数字。

## 11. 最终验收清单

### 可复现性

- [ ] 干净 clone 可完成正式评测；
- [ ] qrels、pool、runs、结果和哈希完整；
- [ ] 依赖版本和运行命令完整；
- [ ] 正式结果与 v1 一致或有版本化变更说明。

### 产品

- [ ] `/v2/chat` 返回文字、结构化手册图和视频；
- [ ] 答案由联合证据生成；
- [ ] 引用可追踪；
- [ ] Tri-Hybrid 在线运行且无静默回退；
- [ ] 用户视频诊断可用，或明确从本次范围移出；
- [ ] 部署、鉴权、日志、监控和资源释放完成；
- [ ] P95 和安全降级通过。

### 评测

- [ ] Recall@5 问题得到优化或正式解释；
- [ ] 时间 IoU/mAP 完成；
- [ ] 端到端答案和媒体有效率完成；
- [ ] 诊断 Macro-F1 完成；
- [ ] 外部或跨产品泛化完成；
- [ ] 泄漏项完成裁决。

### 论文

- [ ] 完整英文论文；
- [ ] 所有图表自动生成；
- [ ] 方法、数据、标注和评测口径准确；
- [ ] 限制和授权披露完整；
- [ ] 投稿期刊已复核；
- [ ] 投稿材料齐全。

只有上述四部分全部通过，项目状态才能从：

```text
Research prototype / formal retrieval benchmark
```

更新为：

```text
Deployable product candidate / SCI submission ready
```
