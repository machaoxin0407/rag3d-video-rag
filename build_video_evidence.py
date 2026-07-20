#!/usr/bin/env python3
"""Fuse video scenes, ASR, and OCR into retrieval-ready evidence objects."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.evidence import (
    DEFAULT_ASR_RUNS,
    DEFAULT_ASR_SEGMENTS,
    DEFAULT_OCR,
    DEFAULT_OCR_RUNS,
    DEFAULT_OUTPUT,
    DEFAULT_PREPROCESSING,
    DEFAULT_SCENES,
    DEFAULT_VLM_CAPTIONS,
    DEFAULT_VLM_RUNS,
    build_evidence_manifest,
)


def parse_args() -> argparse.Namespace:
    """Parse all stage manifest paths used for evidence fusion."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--preprocessing", type=Path, default=DEFAULT_PREPROCESSING)
    parser.add_argument("--scenes", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--asr-runs", type=Path, default=DEFAULT_ASR_RUNS)
    parser.add_argument("--asr-segments", type=Path, default=DEFAULT_ASR_SEGMENTS)
    parser.add_argument("--ocr-runs", type=Path, default=DEFAULT_OCR_RUNS)
    parser.add_argument("--ocr", type=Path, default=DEFAULT_OCR)
    parser.add_argument("--vlm-runs", type=Path, default=DEFAULT_VLM_RUNS)
    parser.add_argument("--vlm-captions", type=Path, default=DEFAULT_VLM_CAPTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Build the unified evidence manifest and print modality counts."""
    args = parse_args()
    rows = build_evidence_manifest(
        preprocessing_path=args.preprocessing,
        scenes_path=args.scenes,
        asr_runs_path=args.asr_runs,
        asr_segments_path=args.asr_segments,
        ocr_runs_path=args.ocr_runs,
        ocr_path=args.ocr,
        vlm_runs_path=args.vlm_runs,
        vlm_captions_path=args.vlm_captions,
        output_path=args.output,
    )
    counts = {
        kind: sum(row["evidence_type"] == kind for row in rows)
        for kind in ("video_scene", "speech_segment", "frame_text")
    }
    print(f"evidence_complete total={len(rows)} counts={counts}")


if __name__ == "__main__":
    main()
