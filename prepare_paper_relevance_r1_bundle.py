#!/usr/bin/env python3
"""Prepare a self-contained single-reviewer bundle for paper relevance labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from video_rag.manifest_io import ROOT, project_path
from video_rag.relevance_annotation import DEFAULT_OUTPUT, read_csv


DEFAULT_BLIND = ROOT / "data_video" / "review" / "paper_relevance_pool_blind_v1.csv"
DEFAULT_SCENES = ROOT / "data_video" / "manifests" / "scene_manifest.csv"
DEFAULT_BUNDLE = ROOT / "data_video" / "review" / "paper_relevance_r1_bundle_v1"
REVIEW_FIELDS = [
    "query_id", "query_text", "language", "product_class", "query_type", "split",
    "candidate_scene_id", "record_id", "scene_start_time", "scene_end_time",
    "media_relative_path", "thumbnail_relative_path", "scene_text", "blind_order",
    "ai_relevance_grade", "ai_start_time", "ai_end_time", "ai_evidence",
    "ai_evidence_sources", "ai_uncertainty", "ai_uncertainty_reason", "reviewer_id",
    "r1_relevance_grade", "r1_start_time", "r1_end_time", "r1_source_leakage",
    "r1_evidence_notes", "correction_reason", "review_status", "reviewed_at",
]
MEDIA_FIELDS = [
    "candidate_scene_id", "record_id", "source_clip_path", "bundled_clip_path",
    "clip_bytes", "clip_sha256", "source_thumbnail_path", "bundled_thumbnail_path",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind", type=Path, default=DEFAULT_BLIND)
    parser.add_argument("--ai-labels", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scenes", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--materialize-media", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def safe_materialize(source: Path, target: Path) -> str:
    """Create a hard link, falling back to copy, without replacing existing files."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size != source.stat().st_size:
            raise ValueError(f"Existing bundle media differs in size: {target}")
        return "existing"
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def bundle_relative(path: Path, bundle_dir: Path) -> str:
    return str(path.relative_to(bundle_dir)).replace("\\", "/")


def render_index(rows: list[dict[str, object]]) -> str:
    payload = [
        {
            "query_id": row["query_id"],
            "query_text": row["query_text"],
            "product_class": row["product_class"],
            "query_type": row["query_type"],
            "scene_id": row["candidate_scene_id"],
            "record_id": row["record_id"],
            "blind_order": row["blind_order"],
            "ai_grade": row["ai_relevance_grade"],
            "ai_uncertainty": row["ai_uncertainty"],
            "clip": row["media_relative_path"],
            "thumbnail": row["thumbnail_relative_path"],
        }
        for row in rows
    ]
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>R1 相关性复核</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f4f7fb;color:#172033}}
header{{position:sticky;top:0;background:#17324d;color:white;padding:16px 22px;z-index:2}}
h1{{font-size:20px;margin:0 0 10px}} input,select{{padding:8px;border-radius:6px;border:1px solid #aeb8c4}}
main{{padding:18px 22px}} table{{width:100%;border-collapse:collapse;background:white}}
th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}
th{{background:#eaf0f6;position:sticky;top:104px}} tr:hover{{background:#fff8dd}}
.pill{{padding:2px 7px;border-radius:10px;background:#e6eef7;white-space:nowrap}}
a{{color:#0b63a8}} .muted{{color:#607080;font-size:12px}}
</style></head><body>
<header><h1>论文正式 100 问题 · R1 单人复核入口</h1>
<input id="search" size="42" placeholder="搜索问题、场景或记录 ID">
<select id="product"><option value="">全部产品</option></select><span id="count"></span></header>
<main><p class="muted">本页不展示检索方法、排名或分数。最终标签只在 Excel 工作簿中填写。</p>
<table><thead><tr><th>问题</th><th>产品/类型</th><th>场景</th><th>AI 预标注</th><th>媒体</th></tr></thead>
<tbody id="rows"></tbody></table></main>
<script>
const data={data};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const product=document.querySelector('#product');
[...new Set(data.map(x=>x.product_class))].sort().forEach(x=>product.add(new Option(x,x)));
function draw(){{
 const q=document.querySelector('#search').value.toLowerCase(), p=product.value;
 const shown=data.filter(x=>(!p||x.product_class===p)&&(!q||JSON.stringify(x).toLowerCase().includes(q)));
 document.querySelector('#count').textContent=` ${{shown.length}} / ${{data.length}}`;
 document.querySelector('#rows').innerHTML=shown.slice(0,500).map(x=>`<tr>
 <td><b>${{esc(x.query_id)}}</b> ${{esc(x.query_text)}}<br><span class=muted>盲序 ${{esc(x.blind_order)}}</span></td>
 <td><span class=pill>${{esc(x.product_class)}}</span><br>${{esc(x.query_type)}}</td>
 <td>${{esc(x.scene_id)}}<br><span class=muted>${{esc(x.record_id)}}</span></td>
 <td>等级 <b>${{esc(x.ai_grade)}}</b><br><span class=muted>${{esc(x.ai_uncertainty)}}</span></td>
 <td><a href="${{encodeURI(x.clip)}}">播放片段</a> · <a href="${{encodeURI(x.thumbnail)}}">缩略图</a></td>
 </tr>`).join('');
}}
document.querySelector('#search').addEventListener('input',draw);
product.addEventListener('change',draw); draw();
</script></body></html>"""


def main() -> None:
    args = parse_args()
    blind = read_csv(args.blind)
    labels = read_csv(args.ai_labels)
    scenes = {
        row["scene_id"]: row for row in read_csv(args.scenes)
        if row.get("status") == "success"
    }
    label_by_pair = {
        (row["query_id"], row["candidate_scene_id"]): row for row in labels
    }
    if len(label_by_pair) != len(labels):
        raise ValueError("Duplicate AI relevance labels")
    expected_pairs = {
        (row["query_id"], row["candidate_scene_id"]) for row in blind
    }
    if expected_pairs != set(label_by_pair):
        raise ValueError("Blind pool and AI labels differ")

    blind_by_scene: dict[str, dict[str, str]] = {}
    for row in blind:
        existing = blind_by_scene.setdefault(row["candidate_scene_id"], row)
        if existing["thumbnail_path"] != row["thumbnail_path"]:
            raise ValueError(
                f"Candidate scene has inconsistent thumbnails: {row['candidate_scene_id']}"
            )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    media_rows: list[dict[str, object]] = []
    media_by_scene: dict[str, tuple[str, str]] = {}
    for scene_id in sorted({row["candidate_scene_id"] for row in blind}):
        scene = scenes.get(scene_id)
        if not scene:
            raise ValueError(f"Candidate scene is absent from scene manifest: {scene_id}")
        source_clip = project_path(scene["clip_path"])
        source_thumbnail = project_path(blind_by_scene[scene_id]["thumbnail_path"])
        if not source_clip.is_file():
            raise ValueError(f"Missing scene clip: {source_clip}")
        if not source_thumbnail.is_file():
            raise ValueError(f"Missing scene thumbnail: {source_thumbnail}")
        clip_target = output_dir / "items" / scene_id / f"clip{source_clip.suffix.lower() or '.mp4'}"
        thumb_target = output_dir / "items" / scene_id / "thumbnail.jpg"
        if args.materialize_media:
            safe_materialize(source_clip, clip_target)
            safe_materialize(source_thumbnail, thumb_target)
        clip_relative = bundle_relative(clip_target, output_dir)
        thumb_relative = bundle_relative(thumb_target, output_dir)
        media_by_scene[scene_id] = (clip_relative, thumb_relative)
        media_rows.append({
            "candidate_scene_id": scene_id,
            "record_id": scene["record_id"],
            "source_clip_path": scene["clip_path"],
            "bundled_clip_path": clip_relative,
            "clip_bytes": scene["clip_bytes"],
            "clip_sha256": scene["clip_sha256"],
            "source_thumbnail_path": blind_by_scene[scene_id]["thumbnail_path"],
            "bundled_thumbnail_path": thumb_relative,
        })

    review_rows: list[dict[str, object]] = []
    for row in blind:
        key = (row["query_id"], row["candidate_scene_id"])
        label = label_by_pair[key]
        clip_relative, thumb_relative = media_by_scene[row["candidate_scene_id"]]
        review_rows.append({
            "query_id": row["query_id"],
            "query_text": row["query_text"],
            "language": row["language"],
            "product_class": row["product_class"],
            "query_type": row["query_type"],
            "split": row["split"],
            "candidate_scene_id": row["candidate_scene_id"],
            "record_id": row["record_id"],
            "scene_start_time": row["start_seconds"],
            "scene_end_time": row["end_seconds"],
            "media_relative_path": clip_relative,
            "thumbnail_relative_path": thumb_relative,
            "scene_text": row["scene_text"],
            "blind_order": row["blind_order"],
            "ai_relevance_grade": label["ai_relevance_grade"],
            "ai_start_time": label["ai_start_time"],
            "ai_end_time": label["ai_end_time"],
            "ai_evidence": label["ai_evidence"],
            "ai_evidence_sources": label["ai_evidence_sources"],
            "ai_uncertainty": label["ai_uncertainty"],
            "ai_uncertainty_reason": label["ai_uncertainty_reason"],
            "reviewer_id": "R1",
            "r1_relevance_grade": "",
            "r1_start_time": "",
            "r1_end_time": "",
            "r1_source_leakage": "",
            "r1_evidence_notes": "",
            "correction_reason": "",
            "review_status": "pending",
            "reviewed_at": "",
        })
    review_rows.sort(key=lambda row: (row["query_id"], int(row["blind_order"])))
    review_form = output_dir / "review_form.csv"
    media_manifest = output_dir / "bundle_manifest.csv"
    write_csv(review_form, REVIEW_FIELDS, review_rows)
    write_csv(media_manifest, MEDIA_FIELDS, media_rows)
    (output_dir / "index.html").write_text(render_index(review_rows), encoding="utf-8")

    readme = f"""# R1 论文相关性复核包

生成时间：{datetime.now(timezone.utc).isoformat()}

- 问题数：{len({row['query_id'] for row in review_rows})}
- 问题–场景对：{len(review_rows)}
- 唯一场景：{len(media_rows)}
- 媒体模式：{'本地硬链接或复制' if args.materialize_media else '仅生成路径，媒体尚未物化'}

## 使用顺序

1. 打开 `index.html`，按问题或产品查找并播放完整场景片段。
2. 打开 `R1_paper_relevance_review_workbook.xlsx`。
3. 只填写黄色 R1 字段，不修改冻结输入或 AI 原始字段。
4. 0/1 级的 R1 时间边界留空；2/3 级必须填写场景范围内的起止秒。
5. 每行完成后把 `review_status` 改为 `completed`。
6. 不确定时保守判定并在 `r1_evidence_notes` 或 `correction_reason` 中说明。
7. 不得根据检索方法、排名或分数判断；本复核包未包含这些字段。
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    summary = {
        "schema_version": "paper-relevance-r1-bundle-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "queries": len({row["query_id"] for row in review_rows}),
        "pairs": len(review_rows),
        "unique_scenes": len(media_rows),
        "media_materialized": args.materialize_media,
        "review_form_sha256": sha256_file(review_form),
        "media_manifest_sha256": sha256_file(media_manifest),
        "ai_labels_sha256": sha256_file(args.ai_labels),
        "blind_pool_sha256": sha256_file(args.blind),
    }
    (output_dir / "bundle_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"paper_relevance_r1_bundle={output_dir}")


if __name__ == "__main__":
    main()
