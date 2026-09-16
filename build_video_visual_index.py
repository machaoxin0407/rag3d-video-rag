#!/usr/bin/env python3
"""Build a resumable direct-video Qwen3-VL scene embedding index."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from video_rag.dense import DenseSceneIndex, sha256_file
from video_rag.manifest_io import ROOT
from video_rag.retrieval import (
    DEFAULT_EVIDENCE,
    DEFAULT_INVENTORY,
    VideoEvidenceRetriever,
)
from video_rag.visual_model import (
    DEFAULT_VISUAL_IMPLEMENTATION,
    DEFAULT_VISUAL_MODEL,
    VISUAL_IMPLEMENTATION_REVISION,
    VISUAL_MODEL_ID,
    VISUAL_MODEL_REVISION,
    load_visual_embedder,
)


DEFAULT_OUTPUT = (
    ROOT / "data_video" / "indexes" / "video_visual_qwen3_vl_embedding_2b.npz"
)


def parse_args() -> argparse.Namespace:
    """Parse model, source, sampling, and output settings."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_VISUAL_MODEL)
    parser.add_argument(
        "--implementation-root",
        type=Path,
        default=DEFAULT_VISUAL_IMPLEMENTATION,
    )
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--total-pixels", type=int, default=4_194_304)
    return parser.parse_args()


def checkpoint_matches(
    index: DenseSceneIndex,
    evidence_sha256: str,
    inventory_sha256: str,
    args: argparse.Namespace,
) -> bool:
    """Return whether a partial index is safe to resume."""
    metadata = index.metadata
    return (
        metadata.get("schema_version") == "video-visual-index-v1"
        and metadata.get("model_revision") == VISUAL_MODEL_REVISION
        and metadata.get("implementation_revision")
        == VISUAL_IMPLEMENTATION_REVISION
        and metadata.get("evidence_sha256") == evidence_sha256
        and metadata.get("inventory_sha256") == inventory_sha256
        and metadata.get("fps") == args.fps
        and metadata.get("max_frames") == args.max_frames
        and metadata.get("total_pixels") == args.total_pixels
    )


def decoded_video_frames(path: Path) -> int:
    """Count frames through OpenCV before model preprocessing."""
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"OpenCV could not open video: {path}")
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
    if frames <= 0:
        raise ValueError(f"Video has no decodable frames: {path}")
    return frames


def main() -> None:
    """Embed all scene MP4 files, saving a checkpoint after every scene."""
    args = parse_args()
    if args.fps <= 0 or args.max_frames <= 0 or args.total_pixels <= 0:
        raise SystemExit("Sampling arguments must be positive")

    retriever = VideoEvidenceRetriever(
        evidence_path=args.evidence,
        inventory_path=args.inventory,
        mode="bm25",
    )
    expected_ids = [row["evidence_id"] for row in retriever.documents]
    evidence_digest = sha256_file(args.evidence)
    inventory_digest = sha256_file(args.inventory)
    partial_path = args.output.with_suffix(".partial.npz")
    completed_ids: list[str] = []
    vectors: list[np.ndarray] = []
    fallback_scene_ids: list[str] = []
    if partial_path.exists():
        partial = DenseSceneIndex.load(partial_path)
        if checkpoint_matches(partial, evidence_digest, inventory_digest, args):
            if partial.scene_ids == expected_ids[: len(partial.scene_ids)]:
                completed_ids = partial.scene_ids
                vectors = [row for row in partial.vectors]
                fallback_scene_ids = [
                    str(item)
                    for item in partial.metadata.get("fallback_scene_ids", [])
                ]

    model = load_visual_embedder(
        model_path=args.model_path,
        implementation_root=args.implementation_root,
        fps=args.fps,
        max_frames=args.max_frames,
        total_pixels=args.total_pixels,
    )
    null_vector = (
        model.process([{"text": "NULL"}])[0].detach().float().cpu().numpy()
    )
    started = time.perf_counter()
    base_metadata: dict[str, object] = {
        "schema_version": "video-visual-index-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": VISUAL_MODEL_ID,
        "model_revision": VISUAL_MODEL_REVISION,
        "implementation_revision": VISUAL_IMPLEMENTATION_REVISION,
        "embedding_dimension": 2048,
        "document_modality": "video_with_single_frame_image_fallback",
        "document_instruction": None,
        "fps": args.fps,
        "max_frames": args.max_frames,
        "total_pixels": args.total_pixels,
        "evidence_sha256": evidence_digest,
        "inventory_sha256": inventory_digest,
        "normalized": True,
    }
    for index in range(len(completed_ids), len(retriever.documents)):
        row = retriever.documents[index]
        clip_path = (ROOT / row["media_path"]).resolve()
        if not clip_path.is_file():
            raise FileNotFoundError(clip_path)
        if decoded_video_frames(clip_path) < 2:
            thumbnail_path = (ROOT / row["thumbnail_path"]).resolve()
            if not thumbnail_path.is_file():
                raise FileNotFoundError(thumbnail_path)
            model_input = {"image": str(thumbnail_path)}
            fallback_scene_ids.append(row["evidence_id"])
        else:
            model_input = {
                "video": str(clip_path),
                "fps": args.fps,
                "max_frames": args.max_frames,
            }
        embedding = model.process([model_input])
        vector = embedding[0].detach().float().cpu().numpy()
        if float(np.dot(vector, null_vector)) > 0.999:
            raise ValueError(
                f"Visual preprocessing fell back to a NULL embedding: "
                f"{row['evidence_id']}"
            )
        completed_ids.append(row["evidence_id"])
        vectors.append(vector)
        checkpoint_metadata = {
            **base_metadata,
            "document_count": len(completed_ids),
            "fallback_scene_ids": fallback_scene_ids,
            "complete": False,
        }
        DenseSceneIndex(
            completed_ids,
            np.asarray(vectors, dtype=np.float32),
            checkpoint_metadata,
        ).save(partial_path)
        print(
            json.dumps(
                {
                    "completed": len(completed_ids),
                    "total": len(expected_ids),
                    "scene_id": row["evidence_id"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    final_metadata = {
        **base_metadata,
        "document_count": len(completed_ids),
        "fallback_scene_ids": fallback_scene_ids,
        "complete": True,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    DenseSceneIndex(
        completed_ids,
        np.asarray(vectors, dtype=np.float32),
        final_metadata,
    ).save(args.output)
    if partial_path.exists():
        partial_path.unlink()
    print(
        f"visual_index_complete scenes={len(completed_ids)} "
        f"dimension=2048 output={args.output}"
    )


if __name__ == "__main__":
    main()
