"""Thin helpers for the walkthrough notebook.

The notebook should read like a story: each step is a one-line call here that
returns a tidy ``pandas.DataFrame`` (which renders as a table in Jupyter). All the
real work lives in the regular modules; this file only orchestrates + formats.

Import-safe: this module does NOT import the Geometric Knowledge Network at import
time, so ``ensure_gkn()`` can set up the path first (GKN-dependent pieces are
imported lazily inside the functions that need them).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from .config import RegulusConfig
from .ingest.base import Provision

DEFAULT_FRAMEWORKS: tuple[str, ...] = ("eu_ai_act", "nist_ai_rmf")


def ensure_gkn() -> None:
    """Make ``geometric_knowledge_network`` importable — installed package, or the
    sibling local checkout — so the notebook runs without a ``pip install``."""
    try:
        import geometric_knowledge_network  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    import sys

    import regulus

    gkn_src = Path(regulus.__file__).resolve().parents[2].parent / "geometric_knowledge_network" / "src"
    if gkn_src.exists():
        sys.path.insert(0, str(gkn_src))
        print(f"[setup] Using local GKN checkout at {gkn_src}")
    else:
        raise ModuleNotFoundError(
            "GKN not found. Install it: "
            "pip install git+https://github.com/minw0607/geometric_knowledge_network"
        )


def config() -> RegulusConfig:
    return RegulusConfig()


def load_provisions(cfg: Optional[RegulusConfig] = None, frameworks: Sequence[str] = DEFAULT_FRAMEWORKS) -> List[Provision]:
    from .standards_loader import StandardsLoader

    return StandardsLoader(cfg or RegulusConfig()).load(framework_ids=list(frameworks))


def provisions_summary(provisions: List[Provision]) -> pd.DataFrame:
    from collections import Counter

    counts = Counter(p.framework_name for p in provisions)
    return pd.DataFrame(sorted(counts.items()), columns=["framework", "provisions"])


def baseline_lookup(provisions: List[Provision], cfg: Optional[RegulusConfig] = None):
    from .lookup import RegulusLookup

    return RegulusLookup(provisions, cfg or RegulusConfig())


def lookup_table(lookup, issue: str, top_k: int = 5) -> pd.DataFrame:
    rows = [
        {"rank": i, "provision": r.provision.citation(), "score": round(r.score, 3), "source": r.provision.source_url}
        for i, r in enumerate(lookup.search(issue, top_k=top_k), 1)
    ]
    return pd.DataFrame(rows)


def crosswalk_lookup(provisions: List[Provision], cfg: Optional[RegulusConfig] = None):
    from .graph_lookup import RegulusGraphLookup

    return RegulusGraphLookup(provisions, cfg or RegulusConfig())


def graph_stats(graph_lookup) -> pd.DataFrame:
    from .graph import graph_summary

    return pd.DataFrame(sorted(graph_summary(graph_lookup.graph).items()), columns=["graph element", "count"])


def crosswalk_table(graph_lookup, issue: str, top_k: int = 3) -> pd.DataFrame:
    rows = []
    for r in graph_lookup.search(issue, top_k=top_k):
        refs = " | ".join(f"{cx.provision.citation()} ({cx.relation})" for cx in r.crosswalks) or "—"
        rows.append(
            {
                "provision": r.provision.citation(),
                "score": round(r.score, 3),
                "risks addressed": ", ".join(r.risks) or "—",
                "cross-framework references (cited)": refs,
            }
        )
    return pd.DataFrame(rows)
