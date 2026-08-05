from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


load_dotenv(_repo_root() / ".env")
# Reuse an existing sibling GKN .env for shared OPENAI_* credentials (Azure/OpenAI),
# so a setup already configured for GKN embeddings also powers Regulus generation.
# Regulus/.env (loaded above) and the real environment take precedence.
_gkn_env = _repo_root().parent / "geometric_knowledge_network" / ".env"
if _gkn_env.exists():
    load_dotenv(_gkn_env, override=False)


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
    # 'auto' = embeddings when a cloud key is available, else TF-IDF. Or force 'tfidf' / 'embedding'.
    retriever: str = field(default_factory=lambda: os.getenv("REGULUS_RETRIEVER", "auto").lower())
    top_k: int = field(default_factory=lambda: int(os.getenv("REGULUS_TOP_K", "5")))
    # Skip non-substantive/procedural provisions (definitions, amendments, entry
    # into force, ...) in retrieval — they impose no obligation and are pure noise
    # as hits. See stoplist.py. Set REGULUS_FILTER_NON_SUBSTANTIVE=0 to disable.
    filter_non_substantive: bool = field(
        default_factory=lambda: os.getenv("REGULUS_FILTER_NON_SUBSTANTIVE", "1") not in ("0", "false", "False")
    )
    # Keep both corpus layers (regulatory vs threat) represented in top-k when
    # both are relevant — see RegulusLookup.search. REGULUS_LAYER_AWARE=0 disables.
    layer_aware: bool = field(
        default_factory=lambda: os.getenv("REGULUS_LAYER_AWARE", "1") not in ("0", "false", "False")
    )
    chunk_size: int = field(default_factory=lambda: int(os.getenv("REGULUS_CHUNK_SIZE", "900")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("REGULUS_CHUNK_OVERLAP", "150")))

    # LLM interpretation layer (optional). Reads the same OPENAI_* env vars as GKN,
    # so an Azure/OpenAI setup configured for embeddings also powers generation.
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    openai_api_version: str = field(default_factory=lambda: os.getenv("OPENAI_API_VERSION", ""))
    openai_generation_model: str = field(default_factory=lambda: os.getenv("OPENAI_GENERATION_MODEL", "gpt-4o-mini"))
    openai_apim_header_name: str = field(default_factory=lambda: os.getenv("OPENAI_APIM_HEADER_NAME", ""))
    openai_apim_subscription_key: str = field(default_factory=lambda: os.getenv("OPENAI_APIM_SUBSCRIPTION_KEY", ""))
