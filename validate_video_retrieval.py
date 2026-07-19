#!/usr/bin/env python3
"""Validate local video ranking, API serialization, and media boundaries."""

from __future__ import annotations

import json

from fastapi import HTTPException

from api_server import (
    ChatResponseData,
    _resolve_video_media,
    _video_response_items,
)
from video_rag.retrieval import VideoEvidenceRetriever


QUERY_CASES = [
    ("如何使用咖啡机制作 espresso？", "Espresso Machine"),
    ("How does a CCD digital camera work?", "Camera"),
    ("洗衣机脱水时是什么状态？", "Washing Machine"),
    ("怎么使用吸尘器？", "Vacuum"),
    ("压力锅工作时是什么样？", "Pressure Cooker"),
    ("打印机如何打印页面？", "Printer"),
]


def main() -> None:
    """Run deterministic query checks without calling an LLM or remote service."""
    retriever = VideoEvidenceRetriever()
    case_results: dict[str, list[str]] = {}
    for query, expected_class in QUERY_CASES:
        results = retriever.search(query, top_k=3)
        if not results:
            raise ValueError(f"No video result for query: {query}")
        if any(result.product_class != expected_class for result in results):
            raise ValueError(f"Cross-product result for query: {query}")
        case_results[query] = [result.scene_id for result in results]

    if retriever.search("订单什么时候发货？"):
        raise ValueError("Service query unexpectedly returned video evidence")
    api_items = _video_response_items("How does a CCD digital camera work?", "tech")
    if not api_items:
        raise ValueError("Technical API video response is empty")
    if _video_response_items("How does a CCD digital camera work?", "service"):
        raise ValueError("Service route unexpectedly returned API video evidence")
    for item in api_items:
        _resolve_video_media(item.clip_url.removeprefix("/video-media/"))
        _resolve_video_media(item.thumbnail_url.removeprefix("/video-media/"))

    blocked = False
    try:
        _resolve_video_media("../.env")
    except HTTPException as exc:
        blocked = exc.status_code == 404
    if not blocked:
        raise ValueError("Media traversal was not rejected")

    response = ChatResponseData(
        answer="answer",
        session_id="validation",
        timestamp=1,
        videos=api_items,
    )
    payload = response.model_dump()
    if len(payload["videos"]) != len(api_items):
        raise ValueError("Video response serialization lost evidence rows")
    print(
        json.dumps(
            {
                "query_cases": len(QUERY_CASES),
                "api_video_results": len(api_items),
                "media_paths_checked": len(api_items) * 2,
                "traversal_blocked": blocked,
                "case_results": case_results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("video_retrieval_validation=OK")


if __name__ == "__main__":
    main()
