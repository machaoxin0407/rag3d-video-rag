"""Fault-tolerant BM25 and dense retrieval over deployable video scenes."""

from __future__ import annotations

import csv
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from rank_bm25 import BM25Okapi

from .dense import (
    DEFAULT_DENSE_INDEX,
    DenseSceneIndex,
    request_query_embedding,
    sha256_file,
)
from .manifest_io import ROOT


DEFAULT_EVIDENCE = ROOT / "data_video" / "manifests" / "video_evidence_manifest.csv"
DEFAULT_INVENTORY = ROOT / "data_video" / "manifests" / "video_source_inventory.csv"
PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "Camera": ("camera", "digital camera", "ccd", "相机", "数码相机", "摄像机"),
    "Espresso Machine": (
        "espresso",
        "coffee machine",
        "coffee maker",
        "咖啡机",
        "浓缩咖啡",
        "咖啡",
    ),
    "Pressure Cooker": ("pressure cooker", "压力锅", "高压锅", "压力烹饪"),
    "Printer": ("printer", "printing", "print", "打印机", "打印"),
    "Vacuum": ("vacuum", "vacuum cleaner", "吸尘器", "真空吸尘"),
    "Washing Machine": (
        "washing machine",
        "washer",
        "laundry",
        "洗衣机",
        "洗衣",
        "脱水",
    ),
}


@dataclass(frozen=True)
class VideoSearchResult:
    """One ranked video scene ready for API serialization and evaluation."""

    scene_id: str
    record_id: str
    product_class: str
    start_seconds: float
    end_seconds: float
    clip_path: str
    thumbnail_path: str
    text: str
    score: float
    retrieval_mode: str = "bm25"
    bm25_score: float | None = None
    dense_score: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return asdict(self)


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese, Latin text, numbers, and model identifiers."""
    lowered = text.casefold().strip()
    if not lowered:
        return []
    tokens = re.findall(r"[a-z0-9][a-z0-9._+/-]*|[\u4e00-\u9fff]+", lowered)
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 1:
            expanded.extend(token[index : index + 2] for index in range(len(token) - 1))
    return expanded


def load_csv(path: Path) -> list[dict[str, str]]:
    """Read one UTF-8 manifest without importing the analysis pipeline."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class VideoEvidenceRetriever:
    """Scene retriever with BM25, dense, and reciprocal-rank fusion modes."""

    VALID_MODES = {"bm25", "dense", "hybrid"}

    def __init__(
        self,
        evidence_path: Path = DEFAULT_EVIDENCE,
        inventory_path: Path = DEFAULT_INVENTORY,
        dense_index_path: Path = DEFAULT_DENSE_INDEX,
        mode: str | None = None,
        dense_endpoint: str | None = None,
        query_encoder: Callable[[str], np.ndarray] | None = None,
    ) -> None:
        inventory = {row["record_id"]: row for row in load_csv(inventory_path)}
        scene_rows = [
            row
            for row in load_csv(evidence_path)
            if row.get("evidence_type") == "video_scene"
        ]
        self.documents: list[dict[str, str]] = []
        self.search_texts: list[str] = []
        for row in scene_rows:
            product_class = inventory[row["record_id"]]["product_class"]
            aliases = PRODUCT_ALIASES.get(product_class, ())
            searchable = " ".join((product_class, *aliases, row.get("text", "")))
            document = dict(row)
            document["product_class"] = product_class
            self.documents.append(document)
            self.search_texts.append(searchable)
        if not self.documents:
            raise ValueError(f"No video_scene evidence in {evidence_path}")

        requested_mode = (mode or os.getenv("VIDEO_RETRIEVAL_MODE", "hybrid")).lower()
        if requested_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported VIDEO_RETRIEVAL_MODE={requested_mode!r}")
        self.mode = requested_mode
        self.dense_endpoint = dense_endpoint or os.getenv("VIDEO_DENSE_ENDPOINT", "")
        self.query_encoder = query_encoder
        self.tokenized_documents = [tokenize(text) for text in self.search_texts]
        self.bm25 = BM25Okapi(self.tokenized_documents)
        self.dense_index: DenseSceneIndex | None = None
        self.dense_index_error: str | None = None
        if dense_index_path.exists():
            try:
                candidate = DenseSceneIndex.load(dense_index_path)
                expected_ids = [row["evidence_id"] for row in self.documents]
                if candidate.scene_ids != expected_ids:
                    raise ValueError("scene order differs from the evidence manifest")
                if candidate.metadata.get("evidence_sha256") != sha256_file(evidence_path):
                    raise ValueError("evidence manifest digest differs")
                if candidate.metadata.get("inventory_sha256") != sha256_file(inventory_path):
                    raise ValueError("inventory manifest digest differs")
                self.dense_index = candidate
            except Exception as exc:  # noqa: BLE001 - stale indexes must not break the API
                self.dense_index_error = str(exc)

    def detect_product_classes(self, query: str) -> set[str]:
        """Infer explicit product classes from bilingual query aliases."""
        lowered = re.sub(r"[-_/]+", " ", query.casefold())
        detected: set[str] = set()
        for product_class, aliases in PRODUCT_ALIASES.items():
            if any(
                re.sub(r"[-_/]+", " ", alias.casefold()) in lowered
                for alias in aliases
            ):
                detected.add(product_class)
        return detected

    def _dense_scores(self, query: str) -> np.ndarray | None:
        if self.dense_index is None:
            return None
        if self.query_encoder is not None:
            vector = np.asarray(self.query_encoder(query), dtype=np.float32)
        elif self.dense_endpoint:
            vector = request_query_embedding(self.dense_endpoint, query)
        else:
            return None
        return self.dense_index.similarities(vector)

    @staticmethod
    def _rank_map(indices: list[int], scores: np.ndarray) -> dict[int, int]:
        ordered = sorted(indices, key=lambda index: (-float(scores[index]), index))
        return {index: rank for rank, index in enumerate(ordered, start=1)}

    def search(
        self,
        query: str,
        top_k: int = 3,
        mode: str | None = None,
    ) -> list[VideoSearchResult]:
        """Return top scene clips and degrade to BM25 if dense search is unavailable."""
        requested_mode = (mode or self.mode).lower()
        if requested_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported retrieval mode: {requested_mode}")
        query_tokens = tokenize(query)
        if not query_tokens or top_k <= 0:
            return []

        bm25_scores = np.asarray(self.bm25.get_scores(query_tokens), dtype=np.float64)
        detected = self.detect_product_classes(query)
        for index, row in enumerate(self.documents):
            if row["product_class"] in detected:
                bm25_scores[index] += 3.0

        dense_scores: np.ndarray | None = None
        if requested_mode in {"dense", "hybrid"}:
            try:
                dense_scores = self._dense_scores(query)
            except Exception:  # noqa: BLE001 - retrieval must keep its lexical fallback
                dense_scores = None
        effective_mode = requested_mode if dense_scores is not None else "bm25"

        eligible: list[int] = []
        for index, row in enumerate(self.documents):
            if detected and row["product_class"] not in detected:
                continue
            # Without an explicit supported product, require lexical domain evidence.
            # This prevents unrelated service questions from receiving arbitrary videos.
            if not detected and bm25_scores[index] <= 0:
                continue
            if effective_mode == "bm25" and bm25_scores[index] <= 0:
                continue
            eligible.append(index)
        if not eligible:
            return []

        bm25_ranks = self._rank_map(eligible, bm25_scores)
        dense_ranks = (
            self._rank_map(eligible, dense_scores)
            if dense_scores is not None
            else {}
        )
        candidates: list[tuple[int, float]] = []
        for index in eligible:
            if effective_mode == "bm25":
                score = float(bm25_scores[index])
            elif effective_mode == "dense":
                score = float(dense_scores[index])
            else:
                # Weighted reciprocal-rank fusion is robust to incomparable raw scores.
                score = (
                    0.45 / (60 + bm25_ranks[index])
                    + 0.55 / (60 + dense_ranks[index])
                )
            candidates.append((index, score))
        candidates.sort(key=lambda item: (-item[1], item[0]))

        results: list[VideoSearchResult] = []
        per_record: dict[str, int] = {}
        for index, score in candidates:
            row = self.documents[index]
            record_id = row["record_id"]
            if per_record.get(record_id, 0) >= 2:
                continue
            per_record[record_id] = per_record.get(record_id, 0) + 1
            results.append(
                VideoSearchResult(
                    scene_id=row["evidence_id"],
                    record_id=record_id,
                    product_class=row["product_class"],
                    start_seconds=float(row["start_seconds"]),
                    end_seconds=float(row["end_seconds"]),
                    clip_path=row["media_path"],
                    thumbnail_path=row["thumbnail_path"],
                    text=row["text"],
                    score=round(score, 6),
                    retrieval_mode=effective_mode,
                    bm25_score=round(float(bm25_scores[index]), 6),
                    dense_score=(
                        round(float(dense_scores[index]), 6)
                        if dense_scores is not None
                        else None
                    ),
                )
            )
            if len(results) >= top_k:
                break
        return results
