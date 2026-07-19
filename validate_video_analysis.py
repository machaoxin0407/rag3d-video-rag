#!/usr/bin/env python3
"""Validate scene, ASR, OCR, and unified video evidence artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "data_video" / "manifests"


def read_csv(name: str) -> list[dict[str, str]]:
    """Read one analysis manifest by filename."""
    path = MANIFEST_ROOT / name
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def project_path(relative: str) -> Path:
    """Resolve and constrain a media path to the project root."""
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {relative}") from exc
    return path


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_scenes(
    preprocessing: dict[str, dict[str, str]], scenes: list[dict[str, str]]
) -> dict[str, int]:
    """Check continuous coverage, clip integrity, and first-frame decoding."""
    import imageio_ffmpeg

    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in scenes:
        if row["status"] != "success":
            raise ValueError(f"Failed scene row: {row['scene_id']}")
        grouped[row["record_id"]].append(row)
    if set(grouped) != set(preprocessing):
        raise ValueError("Scene records do not match preprocessing records")

    total_bytes = 0
    for record_id, rows in grouped.items():
        rows.sort(key=lambda row: float(row["start_seconds"]))
        if abs(float(rows[0]["start_seconds"])) > 0.001:
            raise ValueError(f"{record_id} scene coverage does not start at zero")
        expected_end = float(preprocessing[record_id]["duration_seconds"])
        previous_end = 0.0
        for row in rows:
            start = float(row["start_seconds"])
            end = float(row["end_seconds"])
            if abs(start - previous_end) > 0.002 or end <= start:
                raise ValueError(f"Non-contiguous scene interval: {row['scene_id']}")
            previous_end = end
            clip = project_path(row["clip_path"])
            if not clip.is_file():
                raise ValueError(f"Missing scene clip: {clip}")
            size = clip.stat().st_size
            total_bytes += size
            if size != int(row["clip_bytes"]):
                raise ValueError(f"Clip size mismatch: {row['scene_id']}")
            if sha256_file(clip) != row["clip_sha256"]:
                raise ValueError(f"Clip SHA-256 mismatch: {row['scene_id']}")
            subprocess.run(
                [
                    str(ffmpeg), "-hide_banner", "-loglevel", "error",
                    "-i", str(clip), "-frames:v", "1", "-f", "null", "-",
                ],
                check=True,
            )
        if abs(previous_end - expected_end) > 0.002:
            raise ValueError(f"{record_id} scene coverage does not reach source end")
    return {"scenes": len(scenes), "scene_bytes": total_bytes}


def validate_asr(
    preprocessing: dict[str, dict[str, str]],
    runs: list[dict[str, str]],
    segments: list[dict[str, str]],
) -> dict[str, int]:
    """Check ASR completion, declared counts, words, and timestamp ranges."""
    successful = {row["record_id"]: row for row in runs if row["status"] == "success"}
    if set(successful) != set(preprocessing):
        raise ValueError("ASR runs do not cover every preprocessing record")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    word_count = 0
    for row in segments:
        record_id = row["record_id"]
        duration = float(preprocessing[record_id]["duration_seconds"])
        start = float(row["start_seconds"])
        end = float(row["end_seconds"])
        if start < 0 or end <= start or end > duration + 0.25:
            raise ValueError(f"ASR interval outside source: {row['segment_id']}")
        words = json.loads(row["words_json"])
        word_count += len(words)
        for word in words:
            if float(word["start"]) < start - 0.05 or float(word["end"]) > end + 0.05:
                raise ValueError(f"Word timestamp outside segment: {row['segment_id']}")
        grouped[record_id].append(row)
    for record_id, run in successful.items():
        if int(run["segment_count"]) != len(grouped[record_id]):
            raise ValueError(f"ASR segment count mismatch: {record_id}")
        actual_words = sum(
            len(json.loads(row["words_json"])) for row in grouped[record_id]
        )
        if int(run["word_count"]) != actual_words:
            raise ValueError(f"ASR word count mismatch: {record_id}")
    return {"asr_segments": len(segments), "asr_words": word_count}


def validate_ocr(
    preprocessing: dict[str, dict[str, str]],
    runs: list[dict[str, str]],
    observations: list[dict[str, str]],
) -> dict[str, int]:
    """Check OCR completion, thresholds, frame paths, and source timestamps."""
    successful = {row["record_id"]: row for row in runs if row["status"] == "success"}
    if set(successful) != set(preprocessing):
        raise ValueError("OCR runs do not cover every preprocessing record")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    frames_with_text: dict[str, set[str]] = defaultdict(set)
    for row in observations:
        record_id = row["record_id"]
        duration = float(preprocessing[record_id]["duration_seconds"])
        timestamp = float(row["timestamp_seconds"])
        if not 0 <= timestamp <= duration + 0.001:
            raise ValueError(f"OCR timestamp outside source: {row['observation_id']}")
        if float(row["confidence"]) < float(successful[record_id]["minimum_score"]):
            raise ValueError(f"OCR result below run threshold: {row['observation_id']}")
        if not project_path(row["frame_path"]).is_file():
            raise ValueError(f"Missing OCR frame: {row['frame_path']}")
        json.loads(row["polygon_json"])
        grouped[record_id].append(row)
        frames_with_text[record_id].add(row["frame_id"])
    for record_id, run in successful.items():
        if int(run["frame_count"]) != int(preprocessing[record_id]["keyframe_count"]):
            raise ValueError(f"OCR frame count mismatch: {record_id}")
        if int(run["observation_count"]) != len(grouped[record_id]):
            raise ValueError(f"OCR observation count mismatch: {record_id}")
        if int(run["frames_with_text"]) != len(frames_with_text[record_id]):
            raise ValueError(f"OCR text-frame count mismatch: {record_id}")
    return {
        "ocr_observations": len(observations),
        "ocr_frames_with_text": sum(len(frames) for frames in frames_with_text.values()),
    }


def validate_evidence(
    preprocessing: dict[str, dict[str, str]],
    scenes: list[dict[str, str]],
    segments: list[dict[str, str]],
    observations: list[dict[str, str]],
    evidence: list[dict[str, str]],
) -> dict[str, int]:
    """Check unified evidence cardinality, identity, JSON, and media links."""
    identifiers = [row["evidence_id"] for row in evidence]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Evidence identifiers are not unique")
    expected_count = len(scenes) + len(segments) + len(observations)
    if len(evidence) != expected_count:
        raise ValueError("Unified evidence count does not equal stage evidence count")
    valid_hashes = {key: row["source_sha256"] for key, row in preprocessing.items()}
    empty_scene_text = 0
    type_counts = Counter()
    for row in evidence:
        type_counts[row["evidence_type"]] += 1
        if row["record_id"] not in valid_hashes:
            raise ValueError(f"Unknown evidence record: {row['evidence_id']}")
        if row["source_sha256"] != valid_hashes[row["record_id"]]:
            raise ValueError(f"Evidence source hash mismatch: {row['evidence_id']}")
        if not project_path(row["media_path"]).is_file():
            raise ValueError(f"Missing evidence media: {row['evidence_id']}")
        if row["thumbnail_path"] and not project_path(row["thumbnail_path"]).is_file():
            raise ValueError(f"Missing evidence thumbnail: {row['evidence_id']}")
        json.loads(row["metadata_json"])
        if row["evidence_type"] == "video_scene" and not row["text"].strip():
            empty_scene_text += 1
    return {
        "evidence_total": len(evidence),
        "video_scene_evidence": type_counts["video_scene"],
        "speech_evidence": type_counts["speech_segment"],
        "frame_text_evidence": type_counts["frame_text"],
        "empty_scene_text": empty_scene_text,
    }


def main() -> None:
    """Run the full video-analysis validation suite and print JSON metrics."""
    preprocessing_rows = [
        row for row in read_csv("preprocessing_manifest.csv") if row["status"] == "success"
    ]
    preprocessing = {row["record_id"]: row for row in preprocessing_rows}
    scenes = read_csv("scene_manifest.csv")
    asr_runs = read_csv("asr_runs.csv")
    asr_segments = read_csv("asr_segments.csv")
    ocr_runs = read_csv("ocr_runs.csv")
    observations = read_csv("ocr_observations.csv")
    evidence = read_csv("video_evidence_manifest.csv")
    report = {"records": len(preprocessing)}
    report.update(validate_scenes(preprocessing, scenes))
    report.update(validate_asr(preprocessing, asr_runs, asr_segments))
    report.update(validate_ocr(preprocessing, ocr_runs, observations))
    report.update(
        validate_evidence(preprocessing, scenes, asr_segments, observations, evidence)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("video_analysis_validation=OK")


if __name__ == "__main__":
    main()
