#!/usr/bin/env python3
"""Build a normalized Qwen3 text-embedding index for video scenes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from video_rag.dense import (
    DEFAULT_DENSE_INDEX,
    DEFAULT_MODEL_ID,
    DenseSceneIndex,
    sha256_file,
)
from video_rag.retrieval import (
    DEFAULT_EVIDENCE,
    DEFAULT_INVENTORY,
    VideoEvidenceRetriever,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_DENSE_INDEX)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-cache", type=Path, default=Path("models/qwen3-embedding-0.6b"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def model_revision(model: SentenceTransformer) -> str:
    """Return the downloaded Hugging Face commit when available."""
    first = model._first_module()  # noqa: SLF001 - needed for provenance
    config = getattr(getattr(first, "auto_model", None), "config", None)
    return str(getattr(config, "_commit_hash", "") or "unknown")


def main() -> None:
    args = parse_args()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")

    retriever = VideoEvidenceRetriever(
        evidence_path=args.evidence,
        inventory_path=args.inventory,
        mode="bm25",
    )
    dtype = torch.bfloat16 if args.device.startswith("cuda") else torch.float32
    model = SentenceTransformer(
        args.model,
        cache_folder=str(args.model_cache),
        device=args.device,
        model_kwargs={"dtype": dtype},
    )
    vectors = model.encode(
        retriever.search_texts,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    scene_ids = [row["evidence_id"] for row in retriever.documents]
    metadata: dict[str, object] = {
        "schema_version": "video-dense-index-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": args.model,
        "model_revision": model_revision(model),
        "embedding_dimension": int(np.asarray(vectors).shape[1]),
        "document_prompt": None,
        "document_count": len(scene_ids),
        "evidence_sha256": sha256_file(args.evidence),
        "inventory_sha256": sha256_file(args.inventory),
        "normalized": True,
    }
    DenseSceneIndex(scene_ids, np.asarray(vectors), metadata).save(args.output)
    print(
        f"dense_index_complete scenes={len(scene_ids)} "
        f"dimension={metadata['embedding_dimension']} output={args.output}"
    )
    print(f"model_revision={metadata['model_revision']}")


if __name__ == "__main__":
    main()
