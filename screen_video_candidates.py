#!/usr/bin/env python3
"""Technically screen quarantined videos and create auditable review frames."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCREEN_FIELDS = [
    "record_id",
    "product_class",
    "title",
    "source_platform",
    "candidate_split",
    "local_path",
    "source_sha256",
    "receipt_sha256",
    "bytes",
    "duration_seconds",
    "fps",
    "width",
    "height",
    "video_codec",
    "audio_present",
    "sample_frame_paths",
    "sample_frame_count",
    "duplicate_of",
    "technical_decision",
    "technical_reasons",
    "content_decision",
    "content_reason",
    "screened_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--receipts",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_download_receipts.csv",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "wikimedia_candidates.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_technical_screen.csv",
    )
    parser.add_argument(
        "--frames-dir",
        type=Path,
        default=ROOT / "data_video" / "review" / "candidate_frames",
    )
    parser.add_argument("--min-bytes", type=int, default=500_000)
    parser.add_argument("--min-duration", type=float, default=3.0)
    parser.add_argument("--max-duration", type=float, default=1800.0)
    parser.add_argument("--min-width", type=int, default=320)
    parser.add_argument("--min-height", type=int, default=240)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCREEN_FIELDS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["record_id"]))
    os.replace(temporary, path)


def project_path(value: str) -> Path:
    candidate = (ROOT / value.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {value}") from exc
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata_for(source: Path) -> dict[str, Any]:
    import imageio_ffmpeg

    reader = imageio_ffmpeg.read_frames(str(source), pix_fmt="rgb24")
    try:
        metadata = next(reader)
        next(reader)
    finally:
        reader.close()
    return metadata


def stream_descriptions(ffmpeg: Path, source: Path) -> str:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(source)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.stderr


def sample_offsets(duration: float, count: int) -> list[float]:
    if count <= 0:
        raise ValueError("samples must be greater than zero")
    if duration <= 0:
        return [0.0]
    return [duration * (index + 1) / (count + 1) for index in range(count)]


def extract_samples(
    ffmpeg: Path,
    source: Path,
    destination: Path,
    duration: float,
    count: int,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    expected = [destination / f"sample_{index:02d}.jpg" for index in range(1, count + 1)]
    for output, offset in zip(expected, sample_offsets(duration, count), strict=True):
        temporary = output.with_suffix(".tmp.jpg")
        temporary.unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    str(ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{offset:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=640:-2",
                    "-q:v",
                    "2",
                    str(temporary),
                    "-y",
                ],
                check=True,
            )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return expected


def value_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def value_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def split_from_inventory(row: dict[str, str]) -> str:
    notes = row.get("notes", "")
    if "source_disjoint_test_candidate" in notes:
        return "source_disjoint_test_candidate"
    if "development_candidate" in notes:
        return "development_candidate"
    return "unassigned_candidate"


def screen_one(
    receipt: dict[str, str],
    inventory: dict[str, str],
    ffmpeg: Path,
    args: argparse.Namespace,
    first_by_digest: dict[str, str],
) -> dict[str, str]:
    record_id = receipt["record_id"]
    source = project_path(receipt["local_path"])
    reasons: list[str] = []
    digest = ""
    metadata: dict[str, Any] = {}
    sample_paths: list[Path] = []
    descriptions = ""
    duplicate_of = ""

    try:
        if not source.exists():
            raise FileNotFoundError(source)
        size_bytes = source.stat().st_size
        digest = sha256_file(source)
        if digest != receipt.get("sha256", ""):
            reasons.append("sha256_mismatch")
        if digest in first_by_digest:
            duplicate_of = first_by_digest[digest]
            reasons.append("exact_duplicate")
        else:
            first_by_digest[digest] = record_id
        metadata = metadata_for(source)
        descriptions = stream_descriptions(ffmpeg, source)
        duration = value_float(metadata.get("duration"))
        size = metadata.get("size") or metadata.get("source_size") or (0, 0)
        width, height = value_int(size[0]), value_int(size[1])
        if size_bytes < args.min_bytes:
            reasons.append("file_too_small")
        if duration < args.min_duration:
            reasons.append("duration_too_short")
        if duration > args.max_duration:
            reasons.append("duration_too_long")
        if width < args.min_width or height < args.min_height:
            reasons.append("resolution_too_low")
        if duration > 0 and width > 0 and height > 0:
            sample_paths = extract_samples(
                ffmpeg,
                source,
                args.frames_dir / record_id,
                duration,
                args.samples,
            )
    except Exception as exc:  # Continue screening the remaining quarantine batch.
        size_bytes = source.stat().st_size if source.exists() else 0
        reasons.append(f"decode_error:{type(exc).__name__}:{exc}")

    duration = value_float(metadata.get("duration"))
    size = metadata.get("size") or metadata.get("source_size") or (0, 0)
    width, height = value_int(size[0]), value_int(size[1])
    decision = "pass" if not reasons else "fail"
    return {
        "record_id": record_id,
        "product_class": inventory.get("product_class", ""),
        "title": inventory.get("title", ""),
        "source_platform": inventory.get("source_platform", ""),
        "candidate_split": split_from_inventory(inventory),
        "local_path": receipt.get("local_path", ""),
        "source_sha256": digest,
        "receipt_sha256": receipt.get("sha256", ""),
        "bytes": str(size_bytes),
        "duration_seconds": f"{duration:.3f}" if duration else "",
        "fps": str(metadata.get("fps", "")),
        "width": str(width) if width else "",
        "height": str(height) if height else "",
        "video_codec": str(metadata.get("codec", "")).rstrip(","),
        "audio_present": "yes" if "Audio:" in descriptions else "no",
        "sample_frame_paths": "|".join(
            str(path.relative_to(ROOT)) for path in sample_paths
        ),
        "sample_frame_count": str(len(sample_paths)),
        "duplicate_of": duplicate_of,
        "technical_decision": decision,
        "technical_reasons": "|".join(reasons),
        "content_decision": "pending" if decision == "pass" else "not_reviewed",
        "content_reason": "",
        "screened_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    args = parse_args()
    if args.samples <= 0:
        raise ValueError("--samples must be greater than zero")
    import imageio_ffmpeg

    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    receipts = read_csv(args.receipts)
    inventory = {row["record_id"]: row for row in read_csv(args.inventory)}
    prior = {
        row["record_id"]: row for row in read_csv(args.output)
    } if args.output.exists() else {}
    rows: list[dict[str, str]] = []
    first_by_digest: dict[str, str] = {}
    selected = receipts[: args.limit] if args.limit else receipts
    for index, receipt in enumerate(selected, start=1):
        record_id = receipt["record_id"]
        prior_row = prior.get(record_id)
        if prior_row and prior_row.get("source_sha256") == receipt.get("sha256"):
            rows.append(prior_row)
            digest = prior_row.get("source_sha256", "")
            if digest and not prior_row.get("duplicate_of"):
                first_by_digest.setdefault(digest, record_id)
            print(f"[{index}/{len(selected)}] skipped={record_id}", flush=True)
            continue
        row = screen_one(
            receipt,
            inventory.get(record_id, {}),
            ffmpeg,
            args,
            first_by_digest,
        )
        rows.append(row)
        write_csv(args.output, rows)
        print(
            f"[{index}/{len(selected)}] {row['technical_decision']}={record_id} "
            f"reasons={row['technical_reasons'] or 'none'}",
            flush=True,
        )
    write_csv(args.output, rows)
    passed = sum(row["technical_decision"] == "pass" for row in rows)
    print(f"screened={len(rows)} passed={passed} failed={len(rows) - passed}")


if __name__ == "__main__":
    main()
