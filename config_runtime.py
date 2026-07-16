"""安全的默认运行配置。

本文件只保存非敏感默认值。API Key、Bearer Token、邮箱密码等秘密必须通过
进程环境、项目根目录下未纳入 Git 的 ``.env``，或部署平台 Secret 注入。
``apply_default_env`` 不会覆盖调用方已经设置的环境变量。
"""
from __future__ import annotations

import os


DEFAULT_ENV = {
    # 请求限制。
    "CHAT_TIMEOUT_S": "50",
    "CHAT_MULTIMODAL_TIMEOUT_S": "60",
    "CHAT_MAX_IMAGES": "3",
    "CHAT_MAX_IMAGE_BYTES": str(5 * 1024 * 1024),

    # service / tech 二分类器。DEEPSEEK_API_KEY 必须外部注入。
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_BINARY_MODEL": "deepseek-v4-flash",
    "DEEPSEEK_BINARY_TIMEOUT": "3",
    "DEEPSEEK_BINARY_MAX_TOKENS": "4",

    # 主回答模型。BASE_URL、API_KEY 与实际模型名由部署环境配置。
    "SILICONFLOW_ONLY": "1",
    "SILICONFLOW_MAX_CONCURRENCY": "3",
    "AGENT_MAX_TOKENS": "8192",
    "LLM_TIMEOUT_SECONDS": "30",
    "LLM_TRANSIENT_RETRY_ATTEMPTS": "3",

    # 检索服务。EMBEDDING_API_KEY / RERANK_API_KEY 必须外部注入。
    "EMBEDDING_BASE_URL": "https://api.siliconflow.cn/v1",
    "EMBEDDING_MODEL": "Pro/BAAI/bge-m3",
    "EMBEDDING_MAX_CONCURRENCY": "4",
    "RERANK_BASE_URL": "https://api.siliconflow.cn/v1",
    "RERANK_MODEL_ALIAS": "BAAI/bge-reranker-v2-m3",
    "RERANK_ENABLED": "1",

    # chunk 命中后返回完整 parent section。
    "RETURN_PARENT_SECTION": "1",
}


def apply_default_env() -> None:
    """Apply non-sensitive defaults without overriding caller-provided values."""
    for key, value in DEFAULT_ENV.items():
        os.environ.setdefault(key, value)
