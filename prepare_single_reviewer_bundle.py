#!/usr/bin/env python3
"""Materialize a self-contained folder for the R1 video review workflow."""

from __future__ import annotations

import argparse
import csv
import html
import os
import shutil
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


BUNDLE_FIELDS = [
    "record_id",
    "review_scope",
    "review_priority",
    "ai_expected_product_class",
    "ai_predicted_product_class",
    "title",
    "source_page_url",
    "creator",
    "license_id",
    "candidate_split",
    "ai_decision",
    "ai_procedure_relevance",
    "ai_functional_step_visible",
    "ai_visual_evidence",
    "ai_uncertainty",
    "prescreen_flags",
    "bundle_video_path",
    "bundle_frame_dir",
    "reviewer_id",
    "review_status",
    "license_evidence_status",
    "corrected_product_class",
    "corrected_procedure_relevance",
    "corrected_functional_step_visible",
    "privacy_risk",
    "safety_risk",
    "correction_reason",
    "final_decision",
    "dataset_split",
    "reviewed_at",
]

ANNOTATION_FIELDS = {
    "reviewer_id",
    "review_status",
    "license_evidence_status",
    "corrected_product_class",
    "corrected_procedure_relevance",
    "corrected_functional_step_visible",
    "privacy_risk",
    "safety_risk",
    "correction_reason",
    "final_decision",
    "dataset_split",
    "reviewed_at",
}

PENDING_DEFAULTS = {
    "license_evidence_status": "pending",
    "final_decision": "pending",
    "dataset_split": "pending",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_review_queue.csv",
    )
    parser.add_argument("--technical-screen", type=Path, action="append", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data_video" / "review" / "single_reviewer_bundle",
    )
    parser.add_argument(
        "--link-mode",
        choices=("auto", "hardlink", "copy"),
        default="auto",
        help="auto tries a hard link first and copies only when linking is unavailable",
    )
    parser.add_argument(
        "--refresh-form",
        action="store_true",
        help="replace review_form.csv only when every existing row is still pending",
    )
    return parser.parse_args()


def index_technical(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_csv(path):
            record_id = row["record_id"]
            if record_id in rows:
                raise ValueError(f"Duplicate technical row: {record_id}")
            rows[record_id] = row
    return rows


def materialize(source: Path, destination: Path, mode: str) -> str:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.stat().st_size != source.stat().st_size:
            raise ValueError(f"Existing bundle file has a different size: {destination}")
        return "existing"
    if mode in {"auto", "hardlink"}:
        try:
            os.link(source, destination)
            return "hardlink"
        except OSError:
            if mode == "hardlink":
                raise
    shutil.copy2(source, destination)
    return "copy"


def existing_form_has_work(path: Path) -> bool:
    if not path.exists():
        return False
    for row in read_csv(path):
        if row.get("review_status", "pending") != "pending":
            return True
        if any(
            row.get(field, "") not in {"", PENDING_DEFAULTS.get(field, "")}
            for field in ANNOTATION_FIELDS - {"reviewer_id", "review_status"}
        ):
            return True
    return False


def write_instructions(path: Path, total: int, positives: int, audits: int) -> None:
    text = f"""# R1 单人视频复核包

本目录包含 {total} 条待复核记录：{positives} 条 AI 保留项全量复核，{audits} 条 AI 拒绝项抽查。

## 使用顺序

1. 用浏览器打开 `index.html`，按 `high`、`normal`、`audit` 顺序查看。
2. 每条必须播放完整视频；采样帧只用于快速定位，不能代替完整视频。
3. 点击来源页，核对作者、许可证和授权范围。
4. 优先用 Excel 打开 `R1_video_review_workbook.xlsx`；如果该文件尚未生成，再使用 `review_form.csv`。只能填写黄色人工字段，不要修改 `record_id` 和 AI 原始字段。
5. 每完成一条，将 `review_status` 填为 `completed`，填写许可证据、人工修正、风险、最终决定、数据切分和 ISO-8601 时间。
6. 完成后保留原文件名，通知项目维护者执行自动校验并导出规范 CSV。

详细取值和判断规则见项目文档 `docs/AI_SINGLE_REVIEWER_ANNOTATION_PROTOCOL_2026-07-22.md`。
"""
    path.write_text(text, encoding="utf-8")


def write_index(path: Path, rows: list[dict[str, str]]) -> None:
    cards: list[str] = []
    for row in rows:
        record_id = html.escape(row["record_id"])
        title = html.escape(row["title"])
        evidence = html.escape(row["ai_visual_evidence"])
        flags = html.escape(row["prescreen_flags"] or "none")
        source_url = html.escape(row["source_page_url"], quote=True)
        video_path = html.escape(row["bundle_video_path"], quote=True)
        frame_dir = Path(row["bundle_frame_dir"])
        frame_tags = "".join(
            f'<img loading="lazy" src="{html.escape((frame_dir / f"sample_{i:02d}.jpg").as_posix(), quote=True)}" alt="sample {i}">'
            for i in range(1, 6)
        )
        cards.append(
            f"""<section data-priority="{html.escape(row['review_priority'])}">
<h2>{record_id} · {title}</h2>
<p><b>范围：</b>{html.escape(row['review_scope'])}　<b>优先级：</b>{html.escape(row['review_priority'])}</p>
<p><b>类别：</b>{html.escape(row['ai_expected_product_class'])} → {html.escape(row['ai_predicted_product_class'])}</p>
<p><b>AI 证据：</b>{evidence}</p><p><b>预筛标记：</b>{flags}</p>
<p><a href="{source_url}" target="_blank" rel="noreferrer">打开来源与许可证页面</a></p>
<video controls preload="metadata" src="{video_path}"></video>
<div class="frames">{frame_tags}</div>
</section>"""
        )
    page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>R1 视频复核</title><style>
body{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:24px;background:#f5f6f8;color:#172033}
section{background:white;border-radius:12px;padding:20px;margin:0 0 24px;box-shadow:0 2px 10px #0001}
video{width:100%;max-height:650px;background:#000}.frames{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}
.frames img{width:100%;height:140px;object-fit:contain;background:#111}a{color:#075bcc}
@media(max-width:800px){.frames{grid-template-columns:repeat(2,1fr)}}
</style></head><body><h1>R1 单人视频复核</h1><p>先看 high，再看 normal，最后看 audit。完整填写 review_form.csv。</p>
""" + "\n".join(cards) + "</body></html>"
    path.write_text(page, encoding="utf-8")


def main() -> None:
    args = parse_args()
    queue = read_csv(args.queue)
    technical = index_technical(args.technical_screen)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bundle_rows: list[dict[str, str]] = []
    link_counts: dict[str, int] = {}
    for row in queue:
        record_id = row["record_id"]
        if record_id not in technical:
            raise ValueError(f"Review row lacks technical data: {record_id}")
        technical_row = technical[record_id]
        source_video = ROOT / technical_row["local_path"]
        item_dir = args.output_dir / "items" / record_id
        video_destination = item_dir / f"video{source_video.suffix.lower()}"
        result = materialize(source_video, video_destination, args.link_mode)
        link_counts[result] = link_counts.get(result, 0) + 1
        frame_dir = item_dir / "frames"
        for index, frame_text in enumerate(
            technical_row["sample_frame_paths"].split("|"), start=1
        ):
            if not frame_text:
                continue
            frame_result = materialize(
                ROOT / frame_text,
                frame_dir / f"sample_{index:02d}.jpg",
                args.link_mode,
            )
            link_counts[frame_result] = link_counts.get(frame_result, 0) + 1
        bundle_row = {field: row.get(field, "") for field in BUNDLE_FIELDS}
        bundle_row["bundle_video_path"] = video_destination.relative_to(
            args.output_dir
        ).as_posix()
        bundle_row["bundle_frame_dir"] = frame_dir.relative_to(
            args.output_dir
        ).as_posix()
        bundle_rows.append(bundle_row)

    write_csv(args.output_dir / "source_queue_snapshot.csv", BUNDLE_FIELDS, bundle_rows)
    form_path = args.output_dir / "review_form.csv"
    if not form_path.exists():
        write_csv(form_path, BUNDLE_FIELDS, bundle_rows)
    elif args.refresh_form:
        if existing_form_has_work(form_path):
            raise ValueError("Refusing to overwrite review_form.csv with saved review work")
        write_csv(form_path, BUNDLE_FIELDS, bundle_rows)
    write_instructions(
        args.output_dir / "README.md",
        len(bundle_rows),
        sum(row["review_scope"] == "full_positive_review" for row in bundle_rows),
        sum(row["review_scope"] == "rejected_audit_sample" for row in bundle_rows),
    )
    write_index(args.output_dir / "index.html", bundle_rows)
    with (args.output_dir / "bundle_manifest.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("record_id", "video_path", "source_sha256"),
        )
        writer.writeheader()
        for row in bundle_rows:
            writer.writerow(
                {
                    "record_id": row["record_id"],
                    "video_path": row["bundle_video_path"],
                    "source_sha256": technical[row["record_id"]]["source_sha256"],
                }
            )
    print(
        f"bundle={args.output_dir} items={len(bundle_rows)} "
        + " ".join(f"{key}={value}" for key, value in sorted(link_counts.items()))
    )


if __name__ == "__main__":
    main()
