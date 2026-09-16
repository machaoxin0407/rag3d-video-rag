#!/usr/bin/env python3
"""Serve Qwen3-VL text queries for direct-video scene retrieval."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from video_rag.visual_model import (
    DEFAULT_VISUAL_IMPLEMENTATION,
    DEFAULT_VISUAL_MODEL,
    VISUAL_MODEL_ID,
    VISUAL_QUERY_INSTRUCTION,
    load_visual_embedder,
)


HOST = os.getenv("VIDEO_VISUAL_EMBEDDING_HOST", "127.0.0.1")
PORT = int(os.getenv("VIDEO_VISUAL_EMBEDDING_PORT", "8092"))
model = None


class EmbeddingRequest(BaseModel):
    """A bounded batch of text queries."""

    texts: list[str] = Field(min_length=1, max_length=16)


class EmbeddingResponse(BaseModel):
    """Normalized query vectors in the video embedding space."""

    embeddings: list[list[float]]
    model_id: str
    dimension: int
    normalized: bool = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load one BF16 model and release its CUDA allocation on shutdown."""
    global model
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    model = load_visual_embedder(
        model_path=DEFAULT_VISUAL_MODEL,
        implementation_root=DEFAULT_VISUAL_IMPLEMENTATION,
    )
    yield
    model = None
    torch.cuda.empty_cache()


app = FastAPI(title="RAG3D local direct-video query embeddings", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    """Expose readiness and the logical CUDA device."""
    return {
        "ready": model is not None,
        "model_id": VISUAL_MODEL_ID,
        "device": "cuda",
    }


@app.post("/v1/embeddings/query", response_model=EmbeddingResponse)
def embed_query(request: EmbeddingRequest) -> EmbeddingResponse:
    """Embed text queries in the same space as scene videos."""
    if model is None:
        raise RuntimeError("Visual embedding model is not ready")
    vectors = model.process(
        [
            {"text": text, "instruction": VISUAL_QUERY_INSTRUCTION}
            for text in request.texts
        ]
    )
    array = np.asarray(vectors.detach().float().cpu().numpy(), dtype=np.float32)
    return EmbeddingResponse(
        embeddings=array.tolist(),
        model_id=VISUAL_MODEL_ID,
        dimension=int(array.shape[1]),
    )


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, workers=1)
