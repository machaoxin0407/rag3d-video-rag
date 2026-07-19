"""Fast local BM25 retrieval over deployable video-scene evidence."""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

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
    """One ranked video scene ready for API serialization."""

    scene_id: str
    record_id: str
    product_class: str
    start_seconds: float
    end_seconds: float
    clip_path: str
    thumbnail_path: str
    text: str
    score: float

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
    """In-memory BM25 index over scene-level ASR/OCR and product aliases."""

    def __init__(
        self,
        evidence_path: Path = DEFAULT_EVIDENCE,
        inventory_path: Path = DEFAULT_INVENTORY,
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
        self.tokenized_documents = [tokenize(text) for text in self.search_texts]
        self.bm25 = BM25Okapi(self.tokenized_documents)

    def detect_product_classes(self, query: str) -> set[str]:
        """Infer explicit product classes from bilingual query aliases."""
        lowered = query.casefold()
        detected: set[str] = set()
        for product_class, aliases in PRODUCT_ALIASES.items():
            if any(alias.casefold() in lowered for alias in aliases):
                detected.add(product_class)
        return detected

    def search(self, query: str, top_k: int = 3) -> list[VideoSearchResult]:
        """Return top scene clips, restricting to explicit product classes."""
        query_tokens = tokenize(query)
        if not query_tokens or top_k <= 0:
            return []
        scores = np.asarray(self.bm25.get_scores(query_tokens), dtype=np.float64)
        detected = self.detect_product_classes(query)
        candidates: list[tuple[int, float]] = []
        for index, row in enumerate(self.documents):
            product_class = row["product_class"]
            if detected and product_class not in detected:
                continue
            score = float(scores[index])
            if product_class in detected:
                score += 3.0
            if score > 0:
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
                )
            )
            if len(results) >= top_k:
                break
        return results
