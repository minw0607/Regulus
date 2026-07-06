from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


load_dotenv(_repo_root() / ".env")


@dataclass
class RegulusConfig:
    repo_root: Path = field(default_factory=_repo_root)
    cache_dir: Path = field(default_factory=lambda: _repo_root() / "data" / "standards_cache")
    artifacts_dir: Path = field(default_factory=lambda: _repo_root() / "artifacts")

    # Which frameworks to ingest (comma-separated ids); empty = all fetchable.
    frameworks: tuple[str, ...] = field(
        default_factory=lambda: tuple(f.strip() for f in os.getenv("REGULUS_FRAMEWORKS", "").split(",") if f.strip())
    )

    # Retrieval. "tfidf" needs no extra deps; "embedding" uses the GKN embedding
    # store (Azure/OpenAI or local sentence-transformers, per GKN's own env vars).
    retriever: str = field(default_factory=lambda: os.getenv("REGULUS_RETRIEVER", "tfidf").lower())
    top_k: int = field(default_factory=lambda: int(os.getenv("REGULUS_TOP_K", "5")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("REGULUS_CHUNK_SIZE", "900")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("REGULUS_CHUNK_OVERLAP", "150")))
