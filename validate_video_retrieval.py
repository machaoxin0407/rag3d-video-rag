#!/usr/bin/env python3
"""Validate local video ranking, API serialization, and media boundaries."""

from __future__ import annotations

import json

from fastapi import HTTPException
from fastapi.testclient import TestClient

import api_server
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
        if any(result.retrieval_mode not in {"bm25", "dense", "hybrid"} for result in results):
            raise ValueError(f"Unknown retrieval mode for query: {query}")
        case_results[query] = [result.scene_id for result in results]

    if retriever.search("订单什么时候发货？"):
        raise ValueError("Service query unexpectedly returned video evidence")
    api_items = _video_response_items("打印机如何打印页面？", "tech")
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

    original_token = api_server.EXPECTED_TOKEN
    original_runner = api_server._run_agent_sync
    try:
        api_server.EXPECTED_TOKEN = "video-validation-token"
        api_server._run_agent_sync = lambda question, session_id, images: (
            "validated answer",
            [],
            "tech",
            {},
            api_items,
        )
        client = TestClient(api_server.app)
        headers = {"Authorization": "Bearer video-validation-token"}
        chat_response = client.post(
            "/chat",
            headers=headers,
            json={"question": "打印机如何打印页面？", "session_id": "validation"},
        )
        if chat_response.status_code != 200:
            raise ValueError(f"/chat contract failed: {chat_response.text}")
        chat_payload = chat_response.json()
        if len(chat_payload["data"]["videos"]) != len(api_items):
            raise ValueError("/chat response omitted video evidence")
        media_response = client.get(api_items[0].clip_url, headers=headers)
        if media_response.status_code != 200:
            raise ValueError("Authenticated video media request failed")
        if not media_response.headers.get("content-type", "").startswith("video/"):
            raise ValueError("Video media response has an unexpected content type")
        denied_response = client.get("/video-media/../.env", headers=headers)
        if denied_response.status_code == 200:
            raise ValueError("HTTP media traversal was not rejected")
    finally:
        api_server.EXPECTED_TOKEN = original_token
        api_server._run_agent_sync = original_runner
    print(
        json.dumps(
            {
                "query_cases": len(QUERY_CASES),
                "api_video_results": len(api_items),
                "media_paths_checked": len(api_items) * 2,
                "traversal_blocked": blocked,
                "chat_contract_status": chat_response.status_code,
                "media_contract_status": media_response.status_code,
                "case_results": case_results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("video_retrieval_validation=OK")


if __name__ == "__main__":
    main()
