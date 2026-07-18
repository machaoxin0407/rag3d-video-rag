"""Build a unified retrieval manifest from scenes, speech, and frame text."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from .manifest_io import ROOT, read_csv, write_csv


DEFAULT_PREPROCESSING = ROOT / "data_video" / "manifests" / "preprocessing_manifest.csv"
DEFAULT_SCENES = ROOT / "data_video" / "manifests" / "scene_manifest.csv"
DEFAULT_ASR_RUNS = ROOT / "data_video" / "manifests" / "asr_runs.csv"
DEFAULT_ASR_SEGMENTS = ROOT / "data_video" / "manifests" / "asr_segments.csv"
DEFAULT_OCR_RUNS = ROOT / "data_video" / "manifests" / "ocr_runs.csv"
DEFAULT_OCR = ROOT / "data_video" / "manifests" / "ocr_observations.csv"
DEFAULT_OUTPUT = ROOT / "data_video" / "manifests" / "video_evidence_manifest.csv"
EVIDENCE_FIELDS = [
    "evidence_id",
    "record_id",
    "evidence_type",
    "start_seconds",
    "end_seconds",
    "text",
    "media_path",
    "thumbnail_path",
    "source_sha256",
    "language",
    "confidence",
    "asr_segment_ids",
    "ocr_observation_ids",
    "metadata_json",
]


def require_successful_runs(path: Path, expected: set[str], stage: str) -> None:
    """Reject evidence construction when any source-level analysis run failed."""
    rows = read_csv(path)
    successful = {row["record_id"] for row in rows if row.get("status") == "success"}
    if successful != expected:
        missing = sorted(expected - successful)
        extra = sorted(successful - expected)
        raise ValueError(f"{stage} run mismatch; missing={missing}, extra={extra}")


def group_by_record(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group manifest rows by source record while preserving input order."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["record_id"]].append(row)
    return dict(grouped)


def interval_overlap(row: dict[str, str], start: float, end: float) -> bool:
    """Return whether one timed row overlaps a half-open scene interval."""
    return float(row["start_seconds"]) < end and float(row["end_seconds"]) > start


def timestamp_inside(row: dict[str, str], start: float, end: float) -> bool:
    """Return whether an OCR timestamp belongs to a scene interval."""
    timestamp = float(row["timestamp_seconds"])
    return start <= timestamp < end or math.isclose(timestamp, end, abs_tol=0.001)


def scene_for_time(
    scenes: list[dict[str, str]], timestamp: float
) -> dict[str, str] | None:
    """Find the scene containing a timestamp, including the final endpoint."""
    for index, scene in enumerate(scenes):
        start = float(scene["start_seconds"])
        end = float(scene["end_seconds"])
        if start <= timestamp < end or (
            index == len(scenes) - 1 and math.isclose(timestamp, end, abs_tol=0.001)
        ):
            return scene
    return None


def scene_thumbnail(preprocessing: dict[str, str], start: float) -> str:
    """Choose the first uniform keyframe at or immediately before a scene."""
    interval = float(preprocessing["keyframe_interval_seconds"])
    count = int(preprocessing["keyframe_count"])
    index = min(int(start // interval), count - 1)
    return f"{preprocessing['keyframe_dir']}/frame_{index:06d}.jpg"


def compact_json(payload: dict[str, object]) -> str:
    """Serialize evidence metadata deterministically for CSV storage."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def scene_evidence(
    scene: dict[str, str],
    preprocessing: dict[str, str],
    asr_rows: list[dict[str, str]],
    ocr_rows: list[dict[str, str]],
) -> dict[str, str]:
    """Create one deployable video-scene evidence object with fused text."""
    start = float(scene["start_seconds"])
    end = float(scene["end_seconds"])
    speech = [row for row in asr_rows if interval_overlap(row, start, end)]
    frame_text = [row for row in ocr_rows if timestamp_inside(row, start, end)]
    speech_text = " ".join(row["text"] for row in speech if row["text"])
    ocr_text = " ".join(row["text"] for row in frame_text if row["text"])
    pieces = []
    if speech_text:
        pieces.append(f"ASR: {speech_text}")
    if ocr_text:
        pieces.append(f"OCR: {ocr_text}")
    confidences = [
        min(1.0, math.exp(float(row["avg_log_probability"]))) for row in speech
    ] + [float(row["confidence"]) for row in frame_text]
    return {
        "evidence_id": scene["scene_id"],
        "record_id": scene["record_id"],
        "evidence_type": "video_scene",
        "start_seconds": scene["start_seconds"],
        "end_seconds": scene["end_seconds"],
        "text": "\n".join(pieces),
        "media_path": scene["clip_path"],
        "thumbnail_path": scene_thumbnail(preprocessing, start),
        "source_sha256": scene["source_sha256"],
        "language": speech[0]["language"] if speech else "",
        "confidence": f"{sum(confidences) / len(confidences):.6f}" if confidences else "",
        "asr_segment_ids": "|".join(row["segment_id"] for row in speech),
        "ocr_observation_ids": "|".join(row["observation_id"] for row in frame_text),
        "metadata_json": compact_json(
            {
                "clip_bytes": int(scene["clip_bytes"]),
                "clip_sha256": scene["clip_sha256"],
                "detector": scene["detector"],
                "threshold": float(scene["threshold"]),
            }
        ),
    }


def speech_evidence(
    row: dict[str, str], scene: dict[str, str], source_sha256: str
) -> dict[str, str]:
    """Create a fine-grained speech evidence object linked to its scene clip."""
    return {
        "evidence_id": row["segment_id"],
        "record_id": row["record_id"],
        "evidence_type": "speech_segment",
        "start_seconds": row["start_seconds"],
        "end_seconds": row["end_seconds"],
        "text": row["text"],
        "media_path": scene["clip_path"],
        "thumbnail_path": "",
        "source_sha256": source_sha256,
        "language": row["language"],
        "confidence": f"{min(1.0, math.exp(float(row['avg_log_probability']))):.6f}",
        "asr_segment_ids": row["segment_id"],
        "ocr_observation_ids": "",
        "metadata_json": compact_json(
            {
                "compression_ratio": float(row["compression_ratio"]),
                "language_probability": float(row["language_probability"]),
                "no_speech_probability": float(row["no_speech_probability"]),
                "words": json.loads(row["words_json"]),
            }
        ),
    }


def ocr_evidence(
    row: dict[str, str], scene: dict[str, str], source_sha256: str
) -> dict[str, str]:
    """Create a frame-text evidence object linked to its image and scene clip."""
    return {
        "evidence_id": row["observation_id"],
        "record_id": row["record_id"],
        "evidence_type": "frame_text",
        "start_seconds": row["timestamp_seconds"],
        "end_seconds": row["timestamp_seconds"],
        "text": row["text"],
        "media_path": scene["clip_path"],
        "thumbnail_path": row["frame_path"],
        "source_sha256": source_sha256,
        "language": row["language_profile"],
        "confidence": row["confidence"],
        "asr_segment_ids": "",
        "ocr_observation_ids": row["observation_id"],
        "metadata_json": compact_json(
            {
                "frame_id": row["frame_id"],
                "ocr_version": row["ocr_version"],
                "polygon": json.loads(row["polygon_json"]),
            }
        ),
    }


def build_evidence_manifest(
    preprocessing_path: Path = DEFAULT_PREPROCESSING,
    scenes_path: Path = DEFAULT_SCENES,
    asr_runs_path: Path = DEFAULT_ASR_RUNS,
    asr_segments_path: Path = DEFAULT_ASR_SEGMENTS,
    ocr_runs_path: Path = DEFAULT_OCR_RUNS,
    ocr_path: Path = DEFAULT_OCR,
    output_path: Path = DEFAULT_OUTPUT,
) -> list[dict[str, str]]:
    """Validate all stage manifests and emit unified retrieval evidence rows."""
    preprocessing_rows = [
        row for row in read_csv(preprocessing_path) if row.get("status") == "success"
    ]
    preprocessing = {row["record_id"]: row for row in preprocessing_rows}
    expected = set(preprocessing)
    require_successful_runs(asr_runs_path, expected, "ASR")
    require_successful_runs(ocr_runs_path, expected, "OCR")
    scenes = group_by_record(
        [row for row in read_csv(scenes_path) if row.get("status") == "success"]
    )
    if set(scenes) != expected:
        raise ValueError("Scene manifest does not cover every preprocessed record")
    asr = group_by_record(read_csv(asr_segments_path))
    ocr = group_by_record(read_csv(ocr_path))

    evidence: list[dict[str, str]] = []
    for record_id in sorted(expected):
        record_scenes = scenes[record_id]
        record_asr = asr.get(record_id, [])
        record_ocr = ocr.get(record_id, [])
        source_sha256 = preprocessing[record_id]["source_sha256"]
        for scene in record_scenes:
            evidence.append(
                scene_evidence(scene, preprocessing[record_id], record_asr, record_ocr)
            )
        for row in record_asr:
            midpoint = (float(row["start_seconds"]) + float(row["end_seconds"])) / 2
            scene = scene_for_time(record_scenes, midpoint)
            if scene is None:
                raise ValueError(f"No scene for ASR segment {row['segment_id']}")
            evidence.append(speech_evidence(row, scene, source_sha256))
        for row in record_ocr:
            scene = scene_for_time(record_scenes, float(row["timestamp_seconds"]))
            if scene is None:
                raise ValueError(f"No scene for OCR observation {row['observation_id']}")
            evidence.append(ocr_evidence(row, scene, source_sha256))
    identifiers = [row["evidence_id"] for row in evidence]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate evidence identifiers detected")
    write_csv(output_path, EVIDENCE_FIELDS, evidence)
    return evidence
