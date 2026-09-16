"""交付包自检脚本。

该脚本只做本地静态检查，不访问远程模型服务。它覆盖初赛交付最容易漏的点：
核心文件、Markdown 材料、索引资产、脚本权限、Python 语法、注释覆盖率口径、运行痕迹和
源码中的分散密钥。提交前运行一次，可快速判断 `V6_submit_code/` 是否仍像一个干净交付包。
"""
from __future__ import annotations

import ast
import re
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IGNORED_WALK_DIRS = {
    ".git",
    ".venv",
    ".venv-asr",
    ".venv-ocr",
    ".venv-vlm",
    ".venv-embedding",
    ".venv-visual-embedding",
    "venv",
    "models",
    "checkpoints",
    "outputs",
    "logs",
    "traces",
    "__pycache__",
}

REQUIRED_FILES = [
    "README.md",
    "API.md",
    "MANIFEST.md",
    ".env.example",
    "requirements.txt",
    "config_runtime.py",
    "run_api.sh",
    "smoke_test.sh",
    "caption_video_scenes.py",
    "requirements-vlm.txt",
    "api_server.py",
    "agent.py",
    "llm_router.py",
    "retrieval_engine.py",
    "product_router.py",
    "rerank_client.py",
    "submission_utils.py",
    "generate_submission_v5.py",
    "parse_manuals.py",
    "build_retrieval_index.py",
    "validate_performance.py",
    "skills/search_manual.md",
    "data/catalog.json",
    "data/section_chunks.json",
    "data/retrieval_chunks.json",
    "data/product_mapping_final.csv",
    "data/image_captions_v4_final.json",
    "data/index/dense.faiss",
    "data/index/retrieval_index.pkl",
    "delivery_docs/00_提交材料总览.md",
    "delivery_docs/01_API接口说明.md",
    "delivery_docs/02_源码运行说明.md",
    "delivery_docs/03_技术方案说明.md",
    "delivery_docs/04_验证报告.md",
    "validation_outputs/dataset_overview.csv",
    "validation_outputs/routing_validation.csv",
    "validation_outputs/product_router_summary.csv",
    "validation_outputs/product_router_details.csv",
    "validation_outputs/multimodal_format_summary.csv",
    "validation_outputs/multimodal_format_details.csv",
    "validation_outputs/dialogue_api_validation.csv",
    "validation_outputs/validation_summary.md",
    "validation_outputs/validation_summary.json",
]

REQUIRED_DIRS = [
    "data/manual_sections",
    "手册_v4",
    "手册/插图",
    "submissions",
    "validation_outputs",
]

EXECUTABLE_FILES = [
    "run_api.sh",
    "smoke_test.sh",
    "run_video_analysis_stage.sh",
    "setup_video_vlm_environment.sh",
    "setup_video_embedding_environment.sh",
    "video_embedding_service.sh",
    "setup_video_visual_embedding_environment.sh",
    "video_visual_embedding_service.sh",
]

FORBIDDEN_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".bak",
    ".tmp",
    ".trace.jsonl",
    ".raw.jsonl",
    ".ckpt.json",
)

SECRET_RE = re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{18,}")
ALLOWED_SECRET_FILES: set[str] = set()
ALLOWED_SECRET_VALUES: set[str] = set()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def fail(errors: list[str], message: str) -> None:
    errors.append(f"FAIL {message}")


def warn(warnings: list[str], message: str) -> None:
    warnings.append(f"WARN {message}")


def check_required(errors: list[str]) -> None:
    for item in REQUIRED_FILES:
        path = ROOT / item
        if not path.is_file():
            fail(errors, f"缺少文件: {item}")
    for item in REQUIRED_DIRS:
        path = ROOT / item
        if not path.is_dir():
            fail(errors, f"缺少目录: {item}")


def check_executable(errors: list[str]) -> None:
    # Windows/NTFS does not represent the Unix executable bit reliably. The Git
    # index and the Linux deployment validation remain the source of truth.
    if sys.platform == "win32":
        return
    for item in EXECUTABLE_FILES:
        path = ROOT / item
        if path.exists() and not (path.stat().st_mode & stat.S_IXUSR):
            fail(errors, f"脚本没有可执行权限: {item}")


def check_no_generated_artifacts(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if any(part in IGNORED_WALK_DIRS - {"__pycache__"} for part in path.parts):
            continue
        if "__pycache__" in path.parts:
            fail(errors, f"包含 Python 缓存目录/文件: {rel(path)}")
            continue
        if path.is_file() and path.name == ".DS_Store":
            fail(errors, f"包含 macOS 缓存文件: {rel(path)}")
            continue
        if path.is_file() and path.name.endswith(FORBIDDEN_SUFFIXES):
            fail(errors, f"包含不应提交的运行/备份文件: {rel(path)}")


def python_files() -> list[Path]:
    return sorted(path for path in ROOT.glob("*.py") if path.name != "validate_delivery.py") + [ROOT / "validate_delivery.py"]


def check_python_syntax(errors: list[str]) -> None:
    for path in python_files():
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except Exception as exc:  # noqa: BLE001
            fail(errors, f"Python 语法检查失败: {rel(path)} :: {exc}")


def check_comment_coverage(errors: list[str], warnings: list[str]) -> None:
    """用“有 docstring 的函数/类占比”作为交付注释覆盖率口径。

    该口径比简单的 `#` 行数更适合本工程：核心说明集中在模块、函数、类 docstring 和少量
    关键代码块注释中。目标阈值按初赛要求设为 30%。
    """
    total_defs = 0
    documented_defs = 0
    low_files: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        if not defs:
            continue
        documented = [node for node in defs if ast.get_docstring(node)]
        total_defs += len(defs)
        documented_defs += len(documented)
        ratio = len(documented) / len(defs)
        if ratio < 0.20 and path.name not in {"validate_delivery.py"}:
            low_files.append(f"{path.name}={ratio:.0%}")

    ratio = documented_defs / total_defs if total_defs else 1.0
    if ratio < 0.30:
        fail(errors, f"注释覆盖率不足 30%: {ratio:.1%} ({documented_defs}/{total_defs})")
    elif low_files:
        warn(warnings, "部分辅助脚本文档化比例偏低，但整体覆盖率达标: " + ", ".join(low_files))
    print(f"comment_coverage={ratio:.1%} documented_defs={documented_defs} total_defs={total_defs}")


def is_scanned_text_file(path: Path) -> bool:
    if any(part in IGNORED_WALK_DIRS for part in path.parts):
        return False
    if any(part in {"data", "手册", "手册_v4", "submissions"} for part in path.parts):
        return False
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".faiss", ".pkl", ".pdf"}:
        return False
    return path.is_file()


def check_secret_sprawl(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if not is_scanned_text_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in SECRET_RE.finditer(text):
            value = match.group(0)
            if value in ALLOWED_SECRET_VALUES:
                continue
            if path.name in ALLOWED_SECRET_FILES:
                continue
            fail(errors, f"疑似密钥散落在非配置文件: {rel(path)}")
            break


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    check_required(errors)
    check_executable(errors)
    check_no_generated_artifacts(errors)
    check_python_syntax(errors)
    check_comment_coverage(errors, warnings)
    check_secret_sprawl(errors)

    for message in warnings:
        print(message)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print(f"delivery_check=FAILED errors={len(errors)} warnings={len(warnings)}", file=sys.stderr)
        return 1

    print(f"delivery_check=OK warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
