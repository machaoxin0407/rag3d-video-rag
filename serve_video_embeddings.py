#!/usr/bin/env python3
"""Serve Qwen3 query embeddings on a local-only HTTP endpoint."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from video_rag.dense import DEFAULT_MODEL_ID, DEFAULT_QUERY_TASK


MODEL_ID = os.getenv("VIDEO_EMBEDDING_MODEL", DEFAULT_MODEL_ID)
MODEL_CACHE = os.getenv("VIDEO_EMBEDDING_CACHE", "models/qwen3-embedding-0.6b")
DEVICE = os.getenv("VIDEO_EMBEDDING_DEVICE", "cuda:0")
QUERY_TASK = os.getenv("VIDEO_EMBEDDING_QUERY_TASK", DEFAULT_QUERY_TASK)
OFFLINE = os.getenv("VIDEO_EMBEDDING_OFFLINE", "1").lower() not in {"0", "false", "no"}
model: SentenceTransformer | None = None


class EmbeddingRequest(BaseModel):
    """A small bounded batch of user queries."""

    texts: list[str] = Field(min_length=1, max_length=32)


class EmbeddingResponse(BaseModel):
    """Normalized embeddings plus provenance."""

    embeddings: list[list[float]]
    model_id: str
    dimension: int
    normalized: bool = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load one model per worker and release GPU memory on shutdown."""
    global model
    if DEVICE.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    dtype = torch.bfloat16 if DEVICE.startswith("cuda") else torch.float32
    model = SentenceTransformer(
        MODEL_ID,
        cache_folder=MODEL_CACHE,
        device=DEVICE,
        local_files_only=OFFLINE,
        model_kwargs={"dtype": dtype},
    )
    yield
    model = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="RAG3D local video query embeddings", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    """Expose readiness without embedding user data."""
    return {"ready": model is not None, "model_id": MODEL_ID, "device": DEVICE}


@app.post("/v1/embeddings/query", response_model=EmbeddingResponse)
def embed_query(request: EmbeddingRequest) -> EmbeddingResponse:
    """Embed product-support queries with Qwen's instruction format."""
    if model is None:
        raise RuntimeError("Embedding model is not ready")
    prompted = [f"Instruct: {QUERY_TASK}\nQuery:{text}" for text in request.texts]
    vectors = np.asarray(
        model.encode(
            prompted,
            batch_size=min(8, len(prompted)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ),
        dtype=np.float32,
    )
    return EmbeddingResponse(
        embeddings=vectors.tolist(),
        model_id=MODEL_ID,
        dimension=int(vectors.shape[1]),
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("VIDEO_EMBEDDING_HOST", "127.0.0.1"),
        port=int(os.getenv("VIDEO_EMBEDDING_PORT", "8091")),
        workers=1,
    )
