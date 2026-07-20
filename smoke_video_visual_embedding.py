#!/usr/bin/env python3
"""Smoke-test direct text-to-video similarity on two local scene clips."""

from __future__ import annotations

import json

import numpy as np

from video_rag.manifest_io import ROOT
from video_rag.visual_model import VISUAL_QUERY_INSTRUCTION, load_visual_embedder


def main() -> None:
    """Verify dimensions, normalization, and a basic positive/negative ordering."""
    model = load_visual_embedder()
    query = model.process(
        [
            {
                "text": "A printer is feeding paper and a printed image is emerging.",
                "instruction": VISUAL_QUERY_INSTRUCTION,
            }
        ]
    )[0]
    positive = model.process(
        [
            {
                "video": str(
                    (
                        ROOT
                        / "data_video/processed/printer-001/clips/"
                        "printer-001-scene-0001.mp4"
                    ).resolve()
                ),
                "fps": 1.0,
                "max_frames": 8,
            }
        ]
    )[0]
    negative = model.process(
        [
            {
                "video": str(
                    (
                        ROOT
                        / "data_video/processed/pressure-001/clips/"
                        "pressure-001-scene-0001.mp4"
                    ).resolve()
                ),
                "fps": 1.0,
                "max_frames": 8,
            }
        ]
    )[0]
    vectors = np.asarray(
        [
            query.float().cpu().numpy(),
            positive.float().cpu().numpy(),
            negative.float().cpu().numpy(),
        ]
    )
    norms = np.linalg.norm(vectors, axis=1)
    positive_score = float(vectors[0] @ vectors[1])
    negative_score = float(vectors[0] @ vectors[2])
    if vectors.shape != (3, 2048):
        raise ValueError(f"Unexpected embedding shape: {vectors.shape}")
    if not np.allclose(norms, 1.0, atol=5e-3):
        raise ValueError(f"Embeddings are not normalized: {norms}")
    if positive_score <= negative_score:
        raise ValueError(
            "Printer query did not rank the printer clip above the pressure-cooker clip"
        )
    print(
        json.dumps(
            {
                "shape": list(vectors.shape),
                "norms": norms.round(6).tolist(),
                "printer_similarity": round(positive_score, 6),
                "pressure_cooker_similarity": round(negative_score, 6),
            },
            indent=2,
        )
    )
    print("video_visual_embedding_smoke=OK")


if __name__ == "__main__":
    main()
