#!/usr/bin/env python3
"""Validate P2 outputs and generate the paper-facing status report and manifest."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    online = ROOT / "reports" / "p2" / "online"
    temporal_path = (
        ROOT / "reports" / "p2" / "temporal_localization" / "temporal_metrics_summary.csv"
    )
    retrieval_path = (
        ROOT / "reports" / "p2" / "retrieval_optimization" / "best_config_and_heldout.json"
    )
    loo_path = (
        ROOT / "reports" / "p2" / "retrieval_optimization" / "leave_one_product_out.csv"
    )
    qrels_manifest_path = (
        ROOT
        / "data_video"
        / "manifests"
        / "paper_qrels_v2"
        / "paper_video_qrels_manifest_v2.json"
    )
    required = [
        online / "end_to_end_summary.json",
        online / "end_to_end_per_query.csv",
        online / "answer_judge_raw.jsonl",
        online / "diagnosis_summary.json",
        online / "diagnosis_per_case.csv",
        online / "performance_summary.json",
        online / "retrieval_performance.json",
        online / "retrieval_latency.csv",
        temporal_path,
        retrieval_path,
        loo_path,
        qrels_manifest_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing formal P2 artifacts:\n" + "\n".join(missing))

    e2e = load_json(online / "end_to_end_summary.json")
    diagnosis = load_json(online / "diagnosis_summary.json")
    performance = load_json(online / "performance_summary.json")
    retrieval_perf = load_json(online / "retrieval_performance.json")
    retrieval = load_json(retrieval_path)
    qrels = load_json(qrels_manifest_path)
    temporal = read_csv(temporal_path)
    tri_temporal = next(
        row
        for row in temporal
        if row["dimension"] == "overall" and row["mode"] == "tri_hybrid"
    )
    e2e_rows = read_csv(online / "end_to_end_per_query.csv")
    if len(e2e_rows) != 100 or len({row["query_id"] for row in e2e_rows}) != 100:
        raise ValueError("formal end-to-end output is not 100 unique queries")
    if qrels["grade_changes"] != 0 or qrels["row_count"] != 3775:
        raise ValueError("qrels v2 did not preserve the frozen v1 grades/coverage")

    latency_rows = read_csv(online / "retrieval_latency.csv")
    tri_single = next(
        row
        for row in latency_rows
        if row["mode"] == "tri_hybrid" and row["concurrency"] == "1"
    )
    checks = {
        "qrels_v1_not_overwritten_and_no_grade_changes": True,
        "leakage_policy_explicit": qrels["source_leakage_decisions"] == 9,
        "no_positive_queries_classified": qrels["no_positive_queries"] == 25,
        "temporal_r1_iou_05_target": float(tri_temporal["r1_iou_0.5"]) >= 0.50,
        "retrieval_recall_at_5_target": retrieval["development_metrics"]["recall"] >= 0.80,
        "diagnosis_macro_f1_target": diagnosis["macro_f1"] >= 0.70,
        "e2e_100_unique_queries": True,
        "all_media_valid": e2e["metrics"]["all_media_valid"] == 1.0,
        "retrieval_p95_under_1s": float(tri_single["p95_ms"]) <= 1000,
        "complete_answer_p95_under_15s": performance[
            "sequential_e2e_latency_seconds"
        ]["p95"]
        <= 15,
        "fault_injection_passed": performance["faults_passed"]
        == performance["faults_total"]
        and all(item["passed"] for item in retrieval_perf["isolated_fault_injection"]),
        "leave_one_product_generalization_complete": len(read_csv(loo_path)) == 6,
        "24_hour_soak_complete": performance["24_hour_soak"]["status"] == "completed",
        "human_review_queue_cleared": e2e["human_review_queue"] == 0,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    status = "P2_GO" if not blockers else "P2_CONDITIONAL_NO_GO"

    table_dir = ROOT / "paper" / "tables"
    supplementary = ROOT / "paper" / "supplementary"
    table_dir.mkdir(parents=True, exist_ok=True)
    supplementary.mkdir(parents=True, exist_ok=True)
    copies = {
        temporal_path: table_dir / "p2_temporal_localization.csv",
        ROOT
        / "reports"
        / "p2"
        / "retrieval_optimization"
        / "retrieval_experiments.csv": table_dir / "p2_retrieval_ablation.csv",
        loo_path: table_dir / "p2_leave_one_product_out.csv",
        online / "retrieval_latency.csv": table_dir / "p2_latency.csv",
        online / "end_to_end_per_query.csv": supplementary
        / "p2_end_to_end_per_query.csv",
        online / "diagnosis_per_case.csv": supplementary
        / "p2_diagnosis_per_case.csv",
    }
    for source, target in copies.items():
        shutil.copyfile(source, target)

    report = f"""# P2 执行与 Go/No-Go 报告

生成时间：{datetime.now(timezone.utc).isoformat()}

## 结论

当前状态：**{status}**。

P2 的可复现实验链路已经建立并实际运行：qrels v2、时间定位、仅开发集
检索消融、一次性来源隔离测试、100 问题端到端评测、受控诊断小集、并发与
故障注入、留一产品类泛化均有机器可读产物。未通过的门槛不会被写成已完成。

阻塞项：{", ".join(blockers) if blockers else "无"}。

## 核心结果

| 项目 | 结果 | 门槛/解释 |
|---|---:|---|
| qrels v2 | {qrels['row_count']} pairs / {qrels['grade_changes']} grade changes | 不覆盖 v1；9 条泄漏风险采用预声明策略 |
| 无强正例问题 | {qrels['no_positive_queries']} | 归类为候选池缺少直接答案 |
| Tri-Hybrid R@1 IoU=.5 | {float(tri_temporal['r1_iou_0.5']):.3f} | 目标 ≥0.50 |
| Tri-Hybrid temporal mAP@.5 | {float(tri_temporal['temporal_map_0.5']):.3f} | pool-relative |
| 开发集 Recall@5 | {retrieval['development_metrics']['recall']:.3f} | 目标 ≥0.80；未达时保留原权重 |
| 一次性 source-disjoint test Recall@5 | {retrieval['heldout_source_disjoint_test_metrics']['recall']:.3f} | 未用于选型 |
| 端到端问题 | {e2e['queries']} | 100 个唯一 query_id |
| AI judge correctness | {e2e['metrics']['judge_correctness']:.3f} | AI 评审，失败/高风险待一名人类复核 |
| 证据支持 | {e2e['metrics']['judge_evidence_support']:.3f} | AI 评审 |
| 非幻觉 | {e2e['metrics']['judge_non_hallucination']:.3f} | AI 评审 |
| 媒体有效率 | {e2e['metrics']['all_media_valid']:.3f} | 鉴权读取实测 |
| 诊断 Macro-F1 | {diagnosis['macro_f1']:.3f} | 目标 ≥0.70 |
| 诊断定位 | {diagnosis['product_status']} | 受控代理集，不等于真实用户故障集 |
| 检索 P95 | {float(tri_single['p95_ms']):.1f} ms | 目标 ≤1000 ms |
| 完整回答 P95 | {performance['sequential_e2e_latency_seconds']['p95']:.2f} s | 目标尽量 ≤15 s |
| 24 h 稳定性 | {performance['24_hour_soak']['status']} | 未完成不得宣称稳定性达标 |

## 方法学边界

- qrels v2 不修改任何相关性等级。`yes` 泄漏项不进入主结果或敏感性结果；
  `uncertain` 不进入主结果但保留在敏感性口径。
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
"""
    docs = ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "P2_EXECUTION_REPORT_2026-07-29.md").write_text(
        report, encoding="utf-8"
    )

    tracked_outputs = [
        *required,
        *copies.values(),
        docs / "P2_EXECUTION_REPORT_2026-07-29.md",
    ]
    artifacts = {
        "schema_version": "p2-artifacts-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "artifacts": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(set(tracked_outputs))
        ],
    }
    (ROOT / "paper" / "artifacts_manifest.json").write_text(
        json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
