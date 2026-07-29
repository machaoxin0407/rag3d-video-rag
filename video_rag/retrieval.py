"""Fault-tolerant BM25 and dense retrieval over deployable video scenes."""

from __future__ import annotations

import csv
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from rank_bm25 import BM25Okapi

from .dense import (
    DEFAULT_DENSE_INDEX,
    DEFAULT_VISUAL_DENSE_INDEX,
    DenseSceneIndex,
    request_query_embedding,
    sha256_file,
)
from .manifest_io import ROOT


DEFAULT_EVIDENCE = ROOT / "data_video" / "manifests" / "video_evidence_manifest.csv"
DEFAULT_INVENTORY = ROOT / "data_video" / "manifests" / "video_source_inventory.csv"
PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "Air Fryer": ("air fryer", "air-fryer", "airfryer", "空气炸锅", "气炸锅"),
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
    visual_score: float | None = None

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

    VALID_MODES = {"bm25", "dense", "visual", "hybrid", "tri_hybrid"}

    def __init__(
        self,
        evidence_path: Path = DEFAULT_EVIDENCE,
        inventory_path: Path = DEFAULT_INVENTORY,
        dense_index_path: Path = DEFAULT_DENSE_INDEX,
        visual_index_path: Path = DEFAULT_VISUAL_DENSE_INDEX,
        mode: str | None = None,
        dense_endpoint: str | None = None,
        visual_endpoint: str | None = None,
        query_encoder: Callable[[str], np.ndarray] | None = None,
        visual_query_encoder: Callable[[str], np.ndarray] | None = None,
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

        requested_mode = (mode or os.getenv("VIDEO_RETRIEVAL_MODE", "tri_hybrid")).lower()
        if requested_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported VIDEO_RETRIEVAL_MODE={requested_mode!r}")
        self.mode = requested_mode
        self.dense_endpoint = dense_endpoint or os.getenv("VIDEO_DENSE_ENDPOINT", "")
        self.visual_endpoint = visual_endpoint or os.getenv(
            "VIDEO_VISUAL_DENSE_ENDPOINT", ""
        )
        self.query_encoder = query_encoder
        self.visual_query_encoder = visual_query_encoder
        self.tokenized_documents = [tokenize(text) for text in self.search_texts]
        self.bm25 = BM25Okapi(self.tokenized_documents)
        self.dense_index: DenseSceneIndex | None = None
        self.dense_index_error: str | None = None
        self.visual_index: DenseSceneIndex | None = None
        self.visual_index_error: str | None = None
        expected_ids = [row["evidence_id"] for row in self.documents]
        evidence_digest = sha256_file(evidence_path)
        inventory_digest = sha256_file(inventory_path)
        self.dense_index, self.dense_index_error = self._load_valid_index(
            dense_index_path,
            expected_ids,
            evidence_digest,
            inventory_digest,
        )
        self.visual_index, self.visual_index_error = self._load_valid_index(
            visual_index_path,
            expected_ids,
            evidence_digest,
            inventory_digest,
        )

    def health_status(self, probe_endpoints: bool = False) -> dict[str, object]:
        """Describe configured components without hiding a missing production modality."""
        status: dict[str, object] = {
            "requested_mode": self.mode,
            "documents": len(self.documents),
            "bm25_ready": True,
            "dense_index_ready": self.dense_index is not None,
            "visual_index_ready": self.visual_index is not None,
            "dense_index_error": self.dense_index_error,
            "visual_index_error": self.visual_index_error,
            "dense_endpoint_configured": bool(self.dense_endpoint),
            "visual_endpoint_configured": bool(self.visual_endpoint),
        }
        if probe_endpoints:
            status["dense_service"] = self._probe_endpoint(self.dense_endpoint)
            status["visual_service"] = self._probe_endpoint(self.visual_endpoint)
        return status

    @staticmethod
    def _probe_endpoint(endpoint: str) -> dict[str, object]:
        if not endpoint:
            return {"ready": False, "error": "endpoint_not_configured"}
        try:
            import requests

            started = time.monotonic()
            response = requests.get(f"{endpoint.rstrip('/')}/health", timeout=1.0)
            response.raise_for_status()
            return {
                "ready": True,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except Exception as exc:  # noqa: BLE001 - health must remain serializable
            return {"ready": False, "error": str(exc)[:200]}

    @staticmethod
    def _load_valid_index(
        path: Path,
        expected_ids: list[str],
        evidence_digest: str,
        inventory_digest: str,
    ) -> tuple[DenseSceneIndex | None, str | None]:
        """Load an aligned index or return a reason for safe fallback."""
        if not path.exists():
            return None, None
        try:
            candidate = DenseSceneIndex.load(path)
            if candidate.scene_ids != expected_ids:
                raise ValueError("scene order differs from the evidence manifest")
            if candidate.metadata.get("evidence_sha256") != evidence_digest:
                raise ValueError("evidence manifest digest differs")
            if candidate.metadata.get("inventory_sha256") != inventory_digest:
                raise ValueError("inventory manifest digest differs")
            return candidate, None
        except Exception as exc:  # noqa: BLE001 - stale indexes must not break the API
            return None, str(exc)

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

    def _visual_scores(self, query: str) -> np.ndarray | None:
        if self.visual_index is None:
            return None
        if self.visual_query_encoder is not None:
            vector = np.asarray(self.visual_query_encoder(query), dtype=np.float32)
        elif self.visual_endpoint:
            vector = request_query_embedding(
                self.visual_endpoint,
                query,
                timeout_env="VIDEO_VISUAL_DENSE_TIMEOUT_S",
            )
        else:
            return None
        return self.visual_index.similarities(vector)

    @staticmethod
    def _rank_map(indices: list[int], scores: np.ndarray) -> dict[int, int]:
        ordered = sorted(indices, key=lambda index: (-float(scores[index]), index))
        return {index: rank for rank, index in enumerate(ordered, start=1)}

    def search(
        self,
        query: str,
        top_k: int = 3,
        mode: str | None = None,
        strict: bool = False,
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
        # Video retrieval is product-scoped. Generic service questions can share
        # short Chinese n-grams with captions (for example, 什么/为什么), so a
        # positive lexical score alone is not sufficient evidence of intent.
        if not detected:
            return []
        for index, row in enumerate(self.documents):
            if row["product_class"] in detected:
                bm25_scores[index] += 3.0

        dense_scores: np.ndarray | None = None
        if requested_mode in {"dense", "hybrid", "tri_hybrid"}:
            try:
                dense_scores = self._dense_scores(query)
            except Exception:  # noqa: BLE001 - retrieval must keep its lexical fallback
                dense_scores = None
        visual_scores: np.ndarray | None = None
        if requested_mode in {"visual", "tri_hybrid"}:
            try:
                visual_scores = self._visual_scores(query)
            except Exception:  # noqa: BLE001 - retrieval must keep its lexical fallback
                visual_scores = None

        if requested_mode == "dense":
            effective_mode = "dense" if dense_scores is not None else "bm25"
        elif requested_mode == "visual":
            effective_mode = "visual" if visual_scores is not None else "bm25"
        elif requested_mode == "hybrid":
            effective_mode = "hybrid" if dense_scores is not None else "bm25"
        elif requested_mode == "tri_hybrid":
            if dense_scores is not None and visual_scores is not None:
                effective_mode = "tri_hybrid"
            elif dense_scores is not None:
                effective_mode = "hybrid"
            elif visual_scores is not None:
                effective_mode = "visual_hybrid"
            else:
                effective_mode = "bm25"
        else:
            effective_mode = "bm25"

        if strict and effective_mode != requested_mode:
            raise RuntimeError(
                f"requested video retrieval mode {requested_mode!r} is unavailable; "
                f"effective mode would be {effective_mode!r}"
            )

        eligible: list[int] = []
        for index, row in enumerate(self.documents):
            if row["product_class"] not in detected:
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
        visual_ranks = (
            self._rank_map(eligible, visual_scores)
            if visual_scores is not None
            else {}
        )
        candidates: list[tuple[int, float]] = []
        for index in eligible:
            if effective_mode == "bm25":
                score = float(bm25_scores[index])
            elif effective_mode == "dense":
                score = float(dense_scores[index])
            elif effective_mode == "visual":
                score = float(visual_scores[index])
            elif effective_mode == "visual_hybrid":
                score = (
                    0.45 / (60 + bm25_ranks[index])
                    + 0.55 / (60 + visual_ranks[index])
                )
            elif effective_mode == "tri_hybrid":
                score = (
                    0.30 / (60 + bm25_ranks[index])
                    + 0.35 / (60 + dense_ranks[index])
                    + 0.35 / (60 + visual_ranks[index])
                )
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
                    visual_score=(
                        round(float(visual_scores[index]), 6)
                        if visual_scores is not None
                        else None
                    ),
                )
            )
            if len(results) >= top_k:
                break
        return results
