# 视频 VLM 场景描述基线（2026-07-20）

## 结论

已为 11 条授权视频的 25 个场景生成结构化双语视觉描述，并合并到统一视频证据。原先 5 个同时缺少 ASR/OCR 文本的场景现已补齐，`video_scene` 空文本从 5 降为 0。所有 25 条描述当前均为 `pending`，表示通过机器结构校验但尚未完成人工金标准审核。

## 可复现配置

| 项目 | 固定值 |
|---|---|
| 模型 | `Qwen/Qwen3-VL-8B-Instruct` |
| 模型修订 | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| 精度/设备 | BF16，单张 RTX 4090 24GB，`cuda:0` |
| Transformers | 4.57.1 |
| PyTorch / TorchVision | 2.7.0+cu128 / 0.22.0+cu128 |
| 提示词版本 | `catalog-grounded-visible-scene-json-v2` |
| 输入 | 每场景 1–3 张内部时间点审计帧 |
| 审计帧总数 | 63 |
| 模型缓存 | `models/qwen3-vl-8b`（Git 忽略） |
| 审计帧 | `data_video/vlm_frames`（Git 忽略） |

产品清单中的 `product_class` 只用于消除低分辨率画面中的通用设备歧义。提示词明确禁止从类别标签推断型号、功能、规格、危险或不可见动作。该上下文必须在论文方法和消融实验中披露，并至少比较“有/无 catalog grounding”。

## 机器验收结果

| 指标 | 结果 |
|---|---:|
| VLM 成功场景 | 25/25 |
| 双语摘要完整 | 25/25 |
| 结构化清单完整 | 25/25 |
| 待人工复核 | 25 |
| 统一证据对象 | 448 |
| 空 `video_scene` 文本 | 0 |
| 视频检索回归查询 | 6/6 通过 |
| 推理后项目 GPU 进程 | 0 |

验收命令：

```bash
./run_video_analysis_stage.sh vlm
./run_video_analysis_stage.sh evidence
.venv/bin/python validate_video_analysis.py
.venv/bin/python validate_video_retrieval.py
```

## 内容质量观察

自动结果不能直接作为论文真值。当前需优先人工复核以下场景：

1. `vacuum-001-scene-0001`：运动模糊严重，模型无法从审计帧识别产品；
2. `espresso-003-scene-0001`：画面是 Moccamaster 滴滤咖啡机，但源清单类别为 `Espresso Machine`，可能是数据类别映射问题；
3. `espresso-001-scene-0009`：标题页不显示机器，模型将可见产品标为 `unknown`，这是合理的不确定输出；
4. `camera-001-scene-0006`：模型把片尾/来源文字放入 safety/warning 字段，需人工改为普通可见文字或删除；
5. `washing-001-scene-0001`：识别到“机器停止前不得开门”的安全文字，需与画面和 OCR 双重核对。

上述问题说明“结构有效”不等于“语义正确”，也为论文中的错误分析提供了真实案例。

## 三人复核流程

- 标注员 A：逐场景检查中英文摘要、产品、部件和动作；
- 标注员 B：独立检查状态、安全文字、不确定性及时间边界；
- 标注员 C：裁决 A/B 分歧，并确认源清单产品类别是否需要修正；
- 有分歧的描述不得标记为 `approved`；
- 对模型文本的人工修改标记为 `corrected`，保留原始模型版本和提示词版本；
- `rejected` 场景不进入论文测试真值，但保留在错误分析清单中。

正式评估集冻结前，应计算产品/动作/状态标签的一致性以及安全文字的逐项一致性；模型生成文本只作为预标注，不得作为评估答案。

## 下一阶段

1. 完成 25 场景的三人复核；
2. 在现有 BM25 上增加 dense text embedding；
3. 分别构造 `ASR-only`、`OCR-only`、`VLM-only`、`ASR+OCR` 和完整融合基线；
4. 建立至少 100 条首批人工检索查询与场景相关性标注；
5. 实现 BM25+dense 融合及跨模态 rerank，再开展独立测试。
