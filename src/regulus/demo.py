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

DEFAULT_FRAMEWORKS: tuple[str, ...] = ("eu_ai_act", "nist_ai_rmf", "nist_ai_600_1", "oecd_ai", "iso_42001")


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


# --- Visualization + multi-sample testing -----------------------------------

_ABBREV = {
    "eu_ai_act": "EU AI Act",
    "nist_ai_rmf": "NIST RMF",
    "nist_ai_600_1": "NIST 600-1",
    "oecd_ai": "OECD",
    "iso_42001": "ISO 42001",
}
_COLORS = {
    "eu_ai_act": "#378add",      # blue
    "nist_ai_rmf": "#1baf7a",    # teal
    "nist_ai_600_1": "#639922",  # green
    "oecd_ai": "#eda100",        # amber
    "iso_42001": "#7f77dd",      # violet
}

# A diverse test set spanning frameworks and risk categories.
SAMPLE_ISSUES = [
    "Our credit model was deployed without testing for demographic bias.",
    "We run real-time facial recognition in public spaces for law enforcement.",
    "There is no post-deployment monitoring for our high-risk AI system.",
    "Our chatbot can produce confident but fabricated answers (hallucinations).",
    "We did not document the data used to train our hiring model.",
    "Users are not told when they are interacting with an AI system.",
    "No human can review or override the model's automated decisions.",
]


def _node_label(node: dict) -> str:
    return f"{_ABBREV.get(node.get('framework_id'), node.get('framework_id',''))}\n{node.get('provision_id','')}"


def sample_report(graph_lookup, issues: Optional[List[str]] = None, top_k: int = 1) -> pd.DataFrame:
    """Run several issues through the crosswalk lookup — a quick 'test suite' table."""
    issues = issues or SAMPLE_ISSUES
    rows = []
    for issue in issues:
        results = graph_lookup.search(issue, top_k=top_k)
        for r in results:
            refs = " | ".join(f"{cx.provision.citation()}" for cx in r.crosswalks) or "—"
            rows.append(
                {
                    "issue": issue,
                    "top provision": r.provision.citation(),
                    "risks": ", ".join(r.risks) or "—",
                    "cross-framework references (cited)": refs,
                }
            )
    return pd.DataFrame(rows)


def draw_framework_map(graph_lookup, figsize=(9, 6), seed: int = 3):
    """Framework-level view: nodes = frameworks (sized by #provisions), edges = number
    of cited crosswalks between them. A readable overview of how the corpus interlinks."""
    plt = _import_matplotlib()
    if plt is None:
        return None
    import networkx as nx
    from collections import Counter

    g = graph_lookup.graph
    prov_counts = Counter(
        g.nodes[n].get("framework_id") for n in g if g.nodes[n].get("node_type") == "Provision"
    )
    pair_counts: Counter = Counter()
    for u, v, d in g.edges(data=True):
        if d.get("edge_type") == "CROSSWALK":
            fu, fv = g.nodes[u].get("framework_id"), g.nodes[v].get("framework_id")
            if fu and fv and fu != fv:
                pair_counts[frozenset((fu, fv))] += 1

    F = nx.Graph()
    for fid, cnt in prov_counts.items():
        F.add_node(fid, provisions=cnt)
    for pair, c in pair_counts.items():
        a, b = tuple(pair)
        F.add_edge(a, b, weight=c)

    pos = nx.spring_layout(F, seed=seed, k=1.4)
    fig, ax = plt.subplots(figsize=figsize)
    nx.draw_networkx_edges(F, pos, width=[F[u][v]["weight"] * 0.25 + 0.5 for u, v in F.edges], alpha=0.5, ax=ax)
    nx.draw_networkx_nodes(
        F, pos, node_size=[prov_counts[n] * 6 + 300 for n in F.nodes],
        node_color=[_COLORS.get(n, "#888") for n in F.nodes], alpha=0.9, ax=ax,
    )
    nx.draw_networkx_labels(F, pos, {n: f"{_ABBREV.get(n, n)}\n({prov_counts[n]})" for n in F.nodes}, font_size=9, ax=ax)
    nx.draw_networkx_edge_labels(F, pos, {(u, v): F[u][v]["weight"] for u, v in F.edges}, font_size=8, ax=ax)
    ax.set_title("Cross-framework crosswalk map  (node size = #provisions, edge label = #crosswalks)")
    ax.axis("off")
    fig.tight_layout()
    return fig


def draw_issue_graph(graph_lookup, issue: str, top_k: int = 2, figsize=(11, 7), seed: int = 5):
    """The regulatory neighborhood of one issue: its top provisions (squares, outlined),
    their cited crosswalk provisions, and the risk categories they address (circles)."""
    plt = _import_matplotlib()
    if plt is None:
        return None
    import networkx as nx

    g = graph_lookup.graph
    results = graph_lookup.search(issue, top_k=top_k)
    seeds = [r.provision.unique_id() for r in results if r.provision.unique_id() in g]
    keep = set(seeds)
    for uid in seeds:
        for nb in g.neighbors(uid):
            et = g.edges[uid, nb].get("edge_type")
            if et in ("CROSSWALK", "ADDRESSES"):
                keep.add(nb)
    sub = g.subgraph(keep)

    prov = [n for n in sub if g.nodes[n].get("node_type") == "Provision"]
    risk = [n for n in sub if g.nodes[n].get("node_type") == "RiskCategory"]
    pos = nx.spring_layout(sub, seed=seed, k=0.9)
    fig, ax = plt.subplots(figsize=figsize)
    nx.draw_networkx_edges(sub, pos, alpha=0.35, ax=ax)
    # provisions: colored by framework; seed provisions get a bold outline
    nx.draw_networkx_nodes(
        sub, pos, nodelist=prov, node_shape="s", node_size=900,
        node_color=[_COLORS.get(g.nodes[n].get("framework_id"), "#888") for n in prov],
        edgecolors=["#111" if n in seeds else "none" for n in prov],
        linewidths=[2.0 if n in seeds else 0 for n in prov], alpha=0.9, ax=ax,
    )
    nx.draw_networkx_nodes(sub, pos, nodelist=risk, node_shape="o", node_size=700, node_color="#d3d1c7", alpha=0.9, ax=ax)
    labels = {}
    for n in prov:
        labels[n] = _node_label(g.nodes[n])
    for n in risk:
        labels[n] = g.nodes[n].get("label", n)
    nx.draw_networkx_labels(sub, pos, labels, font_size=7, ax=ax)
    ax.set_title(f"Regulatory neighborhood of the issue\n(bold-outlined = direct hits; circles = risks)")
    ax.axis("off")
    fig.tight_layout()
    return fig


def _import_matplotlib():
    try:
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        print("[note] matplotlib is not installed — run `pip install matplotlib` to draw the graph.")
        return None


# --- LLM interpretation (Phase 4) -------------------------------------------

def interpret(graph_lookup, issue: str, top_k: int = 5, cfg: Optional[RegulusConfig] = None):
    """Generate a grounded, cited interpretation of an issue and render it.

    Retrieves the applicable provisions + their relationships, sends that
    structured context to the configured LLM, and displays the answer. Without an
    API key it renders the structured context it *would* send (dry run). Returns
    the ``Interpretation`` object (inspect ``.context`` / ``.citations``)."""
    from .interpret import RegulusInterpreter

    result = RegulusInterpreter(graph_lookup, cfg or RegulusConfig()).interpret(issue, top_k=top_k)
    text = f"### Regulus — interpretation\n**Issue:** {issue}\n\n{result.display()}"
    try:
        from IPython.display import Markdown, display

        display(Markdown(text))
    except Exception:
        print(text)
    return result
