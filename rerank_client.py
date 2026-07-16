"""
rerank 服务客户端。

当前主线默认对接硅基流动远端 `BAAI/bge-reranker-v2-m3`。
本客户端仍兼容本地 llama-server rerank 接口，但本地 8090 仅作为显式 fallback：
只有设置 `RERANK_BASE_URL=http://127.0.0.1:8090` 时才会使用。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

load_dotenv()

try:
    from config_runtime import apply_default_env

    apply_default_env()
except Exception:
    pass


# 固定默认：硅基流动远端 BAAI/bge-reranker-v2-m3（2026-06-05 用户锁定，本地 8090 不再依赖）。
# 仍可用 RERANK_* 环境变量临时覆盖。
DEFAULT_RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_RERANK_API_KEY = os.getenv("RERANK_API_KEY", "")
DEFAULT_RERANK_MODEL = os.getenv("RERANK_MODEL_ALIAS", "BAAI/bge-reranker-v2-m3")


class RerankError(RuntimeError):
    """Raised when every rerank endpoint/payload attempt fails."""
    pass


@dataclass
class RerankResult:
    """One reranked document index and its relevance score."""
    index: int
    score: float


class RerankClient:
    """Small compatibility client for SiliconFlow and local rerank endpoints."""

    def __init__(
        self,
        base_url: str = DEFAULT_RERANK_BASE_URL,
        api_key: str = DEFAULT_RERANK_API_KEY,
        model: str = DEFAULT_RERANK_MODEL,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RerankResult]:
        """Return documents sorted by rerank score, retrying transient endpoint failures."""
        if not documents:
            return []

        top_n = top_n or len(documents)
        response_payload = None
        last_error: Exception | None = None

        # 瞬时故障（服务过载/返回异常格式）狠狠重试，避免误退回 RRF 污染检索
        for attempt in range(6):
            for endpoint in self._candidate_endpoints():
                for body in self._candidate_payloads(query, documents, top_n):
                    try:
                        response_payload = self._post(endpoint, body)
                        return self._parse_response(response_payload, len(documents))
                    except Exception as exc:
                        last_error = exc
            if attempt < 5:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))

        raise RerankError(f"调用 rerank 服务失败: {last_error}")

    def _candidate_endpoints(self) -> list[str]:
        base = self.base_url.rstrip("/")
        candidates = [
            f"{base}/rerank",
            f"{base}/reranking",
        ]
        if not base.endswith("/v1"):
            candidates.extend(
                [
                    f"{base}/v1/rerank",
                    f"{base}/v1/reranking",
                ]
            )
        return list(dict.fromkeys(candidates))

    def _candidate_payloads(self, query: str, documents: list[str], top_n: int) -> list[dict]:
        return [
            {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            },
            {
                "model": self.model,
                "query": query,
                "texts": documents,
                "top_n": top_n,
                "return_documents": False,
            },
        ]

    def _post(self, endpoint: str, payload: dict) -> dict:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _parse_response(self, payload: dict, total_documents: int) -> list[RerankResult]:
        items = payload.get("results") or payload.get("data") or payload.get("ranked_documents")
        if items is None:
            raise RerankError(f"未知 rerank 返回格式: {payload}")

        results: list[RerankResult] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            index = item.get("index", idx)
            score = item.get("relevance_score", item.get("score", item.get("similarity", 0.0)))
            try:
                index = int(index)
            except (TypeError, ValueError):
                index = idx
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            if 0 <= index < total_documents:
                results.append(RerankResult(index=index, score=score))

        if not results:
            raise RerankError(f"rerank 返回为空: {payload}")

        results.sort(key=lambda item: item.score, reverse=True)
        return results
