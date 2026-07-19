# V6_submit_code 清单

这是 KBrag V6 初赛提交代码目录，目标是方便评审直接启动并验证 `/chat` 服务。

## 包含

### 源码

- `agent.py`
- `api_server.py`
- `llm_router.py`
- `retrieval_engine.py`
- `product_router.py`
- `rerank_client.py`
- `submission_utils.py`
- `generate_submission_v5.py`
- `parse_manuals.py`
- `build_retrieval_index.py`
- `gen_section_summaries.py`
- `embedding_server.py`
- `rerank_server.py`
- `generate_submission_api.py`
- `validate_delivery.py`
- `validate_performance.py`
- `preprocess_video_sources.py`
- `segment_video_sources.py`
- `transcribe_video_sources.py`
- `ocr_video_keyframes.py`
- `build_video_evidence.py`
- `validate_video_analysis.py`
- `validate_video_retrieval.py`
- `video_rag/`

### Prompt / skill

- `skills/search_manual.md`

### 运行数据

- `data/catalog.json`
- `data/section_chunks.json`
- `data/retrieval_chunks.json`
- `data/section_summaries.json`
- `data/section_aliases.json`
- `data/_product_map.json`
- `data/product_mapping_final.csv`
- `data/image_captions_v4_final.json`
- `data/manual_sections/`
- `data/index/dense.faiss`
- `data/index/retrieval_index.pkl`
- `手册_v4/`
- `手册/插图/`
- `data_video/manifests/`（授权、下载、预处理、ASR/OCR、场景与统一证据清单）

### 启动材料

- `README.md`
- `API.md`
- `requirements.txt`
- `config_runtime.py`
- `.env.example`
- `run_api.sh`
- `smoke_test.sh`
- `run_video_analysis_stage.sh`
- `requirements-asr.txt`
- `requirements-ocr.txt`
- `delivery_docs/00_提交材料总览.md`
- `delivery_docs/01_API接口说明.md`
- `delivery_docs/02_源码运行说明.md`
- `delivery_docs/03_技术方案说明.md`
- `delivery_docs/04_验证报告.md`
- `validation_outputs/dataset_overview.csv`
- `validation_outputs/routing_validation.csv`
- `validation_outputs/product_router_summary.csv`
- `validation_outputs/product_router_details.csv`
- `validation_outputs/multimodal_format_summary.csv`
- `validation_outputs/multimodal_format_details.csv`
- `validation_outputs/dialogue_api_validation.csv`
- `validation_outputs/validation_summary.md`
- `validation_outputs/validation_summary.json`
- `submissions/v6_full_reference.csv`
- `submissions/v6_tech_reference.csv`

## 不包含

- `.git/`
- `.claude/`
- `history_versions/`
- `scratch/`
- `reports/`
- `docs_archive/`
- `experiments/`
- `submissions/` 全量历史实验结果
- API 运行 trace/raw 临时日志
- `手册_inlined/`
- Python 缓存和系统临时文件
- 原始视频、生成音频、关键帧、MP4 场景片段与模型权重

## 运行方式

```bash
pip install -r requirements.txt
./run_api.sh
```

另开终端：

```bash
./smoke_test.sh
```

生成或刷新验证报告数据表：

```bash
python validate_performance.py
python validate_performance.py --api-base-url http://127.0.0.1:8000
python validate_video_analysis.py
python validate_video_retrieval.py
```

## 配置说明

`config_runtime.py` 内置了评审启动所需默认配置；环境变量可覆盖默认值。该目录不是公开开源脱敏版，如需公开发布请先完成脱敏和配置替换。
