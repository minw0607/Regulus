"""Graph intelligence — what the knowledge network adds over flat RAG.

Flat RAG retrieves the provisions most *similar* to a scenario and stops there.
Because similarity clusters within a framework (a GenAI scenario pulls a block of
NIST GenAI-Profile actions, say), flat RAG tends to miss the *same concern
expressed in other frameworks* and has no notion of how its hits relate.

This module reads the relationships the graph encodes and turns them into
insights flat RAG cannot produce:

1. ``graph_expand`` — walk the cited CROSSWALK edges (up to a few hops) out of the
   retrieved provisions to surface **related provisions in other frameworks that
   were not individually retrieved**, showing the chain that connects them. This
   is the "one concern, many frameworks" reach.

2. ``prioritize`` — score each retrieved provision by **leverage**: how relevant it
   is *and* how connected it is (frameworks it links to, other findings it shares
   risks with, plus personalized-PageRank centrality in the scenario
   neighborhood). The top one is the **linchpin** — address it first, because
   doing so advances the most other findings.

3. ``rag_vs_graph`` — a side-by-side of what flat similarity surfaces vs what the
   graph surfaces, so the added value is measurable, not asserted.

All of it is deterministic: same scenario + same store ⇒ same result.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx

from .graph_lookup import GraphLookupResult, RegulusGraphLookup
from .risk import RISK_TAXONOMY
from .schema import EdgeType

_CROSSWALK = EdgeType.CROSSWALK.value
_ADDRESSES = EdgeType.ADDRESSES.value


@dataclass
class GraphReach:
    """A provision surfaced by following crosswalk relationships, not similarity."""

    citation: str
    framework: str
    hops: int
    path: List[str]          # chain of citations from a retrieved seed to here
    relation: str            # relation of the final edge
    source: str              # provenance of the final crosswalk mapping
    rationale: str = ""      # the edge's own explanation of WHY the two are linked
    signals: List[str] = field(default_factory=list)  # per-hop "relation: rationale" chain


@dataclass
class PriorityItem:
    citation: str
    framework: str
    relevance: float
    frameworks_linked: List[str]     # distinct frameworks reachable via crosswalks (incl. own)
    risks: List[str]
    connected_findings: List[str]    # other retrieved provisions sharing a risk / crosswalk
    centrality: float                # personalized PageRank in the scenario neighborhood
    priority: float                  # relevance amplified by leverage

    @property
    def leverage(self) -> int:
        """Graph 'blast radius': extra frameworks reached + findings interconnected."""
        return max(0, len(self.frameworks_linked) - 1) + len(self.connected_findings)


def _seed_uids(graph: nx.Graph, results: List[GraphLookupResult]) -> List[str]:
    return [r.provision.unique_id() for r in results if r.provision.unique_id() in graph]


def graph_expand(
    graph_lookup: RegulusGraphLookup, results: List[GraphLookupResult], max_hops: int = 2
) -> List[GraphReach]:
    """Provisions reachable from the retrieved set by walking CROSSWALK edges.

    Returns only provisions that were *not* themselves retrieved, each with the
    shortest crosswalk chain that reaches it — the cross-framework guidance the
    graph adds on top of similarity retrieval.
    """
    g = graph_lookup.graph
    seeds = _seed_uids(g, results)
    seed_set = set(seeds)
    best: Dict[str, GraphReach] = {}

    for seed in seeds:
        # BFS over crosswalk edges only, tracking the citation path AND the
        # per-hop signal chain ("relation: rationale" for every edge walked) —
        # so a reached provision can explain not just *that* it is related but
        # *why*, hop by hop.
        start_label = g.nodes[seed].get("label", seed)
        queue: deque = deque([(seed, 0, [start_label], [])])
        visited = {seed}
        while queue:
            node, hops, path, signals = queue.popleft()
            if hops >= max_hops:
                continue
            for nb in g.neighbors(node):
                edge = g.edges[node, nb]
                if edge.get("edge_type") != _CROSSWALK or nb in visited:
                    continue
                visited.add(nb)
                nb_label = g.nodes[nb].get("label", nb)
                nb_path = path + [nb_label]
                nb_rel = edge.get("relation", "related")
                nb_rat = edge.get("rationale", "")
                nb_src = edge.get("source", "")
                nb_signals = signals + [f"{nb_rel}: {nb_rat}" if nb_rat else nb_rel]
                if nb not in seed_set:
                    prev = best.get(nb)
                    if prev is None or hops + 1 < prev.hops:
                        best[nb] = GraphReach(
                            citation=nb_label,
                            framework=g.nodes[nb].get("framework_name", ""),
                            hops=hops + 1,
                            path=nb_path,
                            relation=nb_rel,
                            source=nb_src,
                            rationale=nb_rat,
                            signals=nb_signals,
                        )
                queue.append((nb, hops + 1, nb_path, nb_signals))

    return sorted(best.values(), key=lambda r: (r.hops, r.framework, r.citation))


def _reachable_frameworks(g: nx.Graph, seed: str, max_hops: int) -> List[str]:
    """Distinct frameworks reachable from ``seed`` via crosswalks (incl. its own)."""
    frameworks = {g.nodes[seed].get("framework_name", "")}
    queue: deque = deque([(seed, 0)])
    visited = {seed}
    while queue:
        node, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for nb in g.neighbors(node):
            if g.edges[node, nb].get("edge_type") != _CROSSWALK or nb in visited:
                continue
            visited.add(nb)
            frameworks.add(g.nodes[nb].get("framework_name", ""))
            queue.append((nb, hops + 1))
    return sorted(f for f in frameworks if f)


def _neighborhood(g: nx.Graph, seeds: List[str]) -> nx.Graph:
    """Seeds + their 1-hop crosswalk neighbours + the risk nodes they address."""
    keep = set(seeds)
    for s in seeds:
        for nb in g.neighbors(s):
            et = g.edges[s, nb].get("edge_type")
            if et in (_CROSSWALK, _ADDRESSES):
                keep.add(nb)
    return g.subgraph(keep)


def _personalized_pagerank(sub: nx.Graph, seeds: List[str], weights: Dict[str, float]) -> Dict[str, float]:
    if sub.number_of_nodes() == 0:
        return {}
    pers = {n: 0.0 for n in sub.nodes}
    total = 0.0
    for s in seeds:
        if s in pers:
            w = max(weights.get(s, 0.0), 0.0) + 1e-6
            pers[s] = w
            total += w
    if total <= 0:  # fall back to uniform over seeds
        for s in seeds:
            if s in pers:
                pers[s] = 1.0
    try:
        return nx.pagerank(sub, personalization=pers, weight=None)
    except Exception:  # pragma: no cover - convergence / empty edge cases
        deg = dict(sub.degree())
        m = max(deg.values()) if deg else 1
        return {n: d / m for n, d in deg.items()}


def prioritize(
    graph_lookup: RegulusGraphLookup, results: List[GraphLookupResult], max_hops: int = 2
) -> List[PriorityItem]:
    """Rank the retrieved provisions by leverage (relevance × connectedness).

    The first item is the linchpin: the provision the graph considers most central
    to the scenario, so addressing it advances the most other findings.
    """
    g = graph_lookup.graph
    seeds = _seed_uids(g, results)
    if not seeds:
        return []
    weights = {r.provision.unique_id(): float(r.score) for r in results}
    risks_by_seed = {r.provision.unique_id(): list(r.risks) for r in results}

    sub = _neighborhood(g, seeds)
    ppr = _personalized_pagerank(sub, seeds, weights)

    items: List[PriorityItem] = []
    for r in results:
        uid = r.provision.unique_id()
        if uid not in g:
            continue
        fw_linked = _reachable_frameworks(g, uid, max_hops)
        my_risks = set(risks_by_seed.get(uid, []))
        # crosswalk neighbours (direct) for interconnection test
        my_xwalk = {nb for nb in g.neighbors(uid) if g.edges[uid, nb].get("edge_type") == _CROSSWALK}
        connected = []
        for other in results:
            ouid = other.provision.unique_id()
            if ouid == uid or ouid not in g:
                continue
            shares_risk = bool(my_risks & set(risks_by_seed.get(ouid, [])))
            linked = ouid in my_xwalk
            if shares_risk or linked:
                connected.append(other.provision.citation())
        centrality = round(ppr.get(uid, 0.0), 4)
        relevance = round(float(r.score), 3)
        leverage = max(0, len(fw_linked) - 1) + len(connected)
        priority = round(relevance * (1 + leverage) + centrality, 4)
        items.append(
            PriorityItem(
                citation=r.provision.citation(),
                framework=r.provision.framework_name,
                relevance=relevance,
                frameworks_linked=fw_linked,
                risks=sorted(my_risks),
                connected_findings=connected,
                centrality=centrality,
                priority=priority,
            )
        )
    items.sort(key=lambda it: (it.priority, it.relevance), reverse=True)
    return items


@dataclass
class RagComparison:
    scenario: str
    top_k: int
    flat_provisions: int
    flat_frameworks: List[str]
    graph_extra_provisions: int
    graph_frameworks: List[str]
    crosswalk_links: int
    risks_identified: List[str]
    linchpin: Optional[str]
    linchpin_is_top1: bool          # did leverage re-rank away from the similarity #1?


@dataclass
class NeighborhoodSummary:
    """Deterministic facts about a scenario's neighborhood — the data behind the
    ``draw_issue_graph`` figure, in structured form for a templated description."""

    scenario: str
    direct_hits: List[str]                         # citations of the retrieved seeds
    reached: List[GraphReach]                       # cross-framework provisions via crosswalks
    frameworks_in_view: List[str]                   # distinct frameworks across hits + reached
    risks: List[Tuple[str, int]] = field(default_factory=list)  # (risk name, #seeds addressing)
    linchpin: Optional[PriorityItem] = None
    shared_risk: Optional[str] = None               # risk addressed by the most seeds

    def to_markdown(self) -> str:
        """A fixed-structure, fully-deterministic reading of the neighborhood."""
        L: List[str] = ["**Reading the neighborhood**\n"]
        L.append(
            f"- **Direct hits ({len(self.direct_hits)}):** "
            + (", ".join(self.direct_hits) if self.direct_hits else "—")
            + ". The provisions this scenario most directly implicates (bold-outlined squares)."
        )
        if self.reached:
            reached_str = ", ".join(f"{r.citation}" for r in self.reached)
            others = [f for f in self.frameworks_in_view]
            L.append(
                f"- **Cross-framework reach ({len(self.reached)}):** following cited crosswalks, the "
                f"graph also connects {reached_str} — the same concern expressed across "
                f"{len(self.frameworks_in_view)} framework(s) ({', '.join(others)}). "
                f"Similarity retrieval alone returned only the direct hits."
            )
        else:
            L.append(
                "- **Cross-framework reach (0):** no further provisions are reachable via crosswalks "
                "from the direct hits (this concern is currently mapped in one framework only)."
            )
        if self.risks:
            risk_str = ", ".join(name for name, _ in self.risks)
            tail = f" *{self.shared_risk}* links the most findings." if self.shared_risk else ""
            L.append(f"- **Risks in play ({len(self.risks)}):** {risk_str} (grey circles).{tail}")
        if self.linchpin is not None:
            lp = self.linchpin
            L.append(
                f"- **Address first — linchpin:** {lp.citation}. The most connected provision — links "
                f"{len(lp.frameworks_linked)} framework(s) and shares risks with "
                f"{len(lp.connected_findings)} other finding(s); fixing it advances the most of the rest."
            )
        return "\n".join(L)


def summarize_neighborhood(
    graph_lookup: RegulusGraphLookup, scenario: str, top_k: int = 3, max_hops: int = 2
) -> NeighborhoodSummary:
    """Compute the deterministic facts describing a scenario's neighborhood."""
    results = graph_lookup.search(scenario, top_k=top_k)
    direct_hits = [r.provision.citation() for r in results]
    reached = graph_expand(graph_lookup, results, max_hops=max_hops)
    frameworks = sorted({r.provision.framework_name for r in results} | {r.framework for r in reached if r.framework})

    risk_counts: Dict[str, int] = {}
    for r in results:
        for risk in r.risks:
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
    risks = sorted(risk_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    shared_risk = next((name for name, c in risks if c > 1), None)

    prio = prioritize(graph_lookup, results, max_hops=max_hops)
    return NeighborhoodSummary(
        scenario=scenario,
        direct_hits=direct_hits,
        reached=reached,
        frameworks_in_view=frameworks,
        risks=risks,
        linchpin=prio[0] if prio else None,
        shared_risk=shared_risk,
    )


def rag_vs_graph(
    graph_lookup: RegulusGraphLookup, scenario: str, top_k: int = 5, max_hops: int = 2
) -> RagComparison:
    """Quantify what the knowledge network adds over flat similarity retrieval."""
    results = graph_lookup.search(scenario, top_k=top_k)
    flat_frameworks = sorted({r.provision.framework_name for r in results})
    reach = graph_expand(graph_lookup, results, max_hops=max_hops)
    graph_frameworks = sorted(set(flat_frameworks) | {r.framework for r in reach if r.framework})
    crosswalk_links = sum(len(r.crosswalks) for r in results)
    risks = sorted({risk for r in results for risk in r.risks})
    prio = prioritize(graph_lookup, results, max_hops=max_hops)
    linchpin = prio[0].citation if prio else None
    top1 = results[0].provision.citation() if results else None
    return RagComparison(
        scenario=scenario,
        top_k=top_k,
        flat_provisions=len(results),
        flat_frameworks=flat_frameworks,
        graph_extra_provisions=len(reach),
        graph_frameworks=graph_frameworks,
        crosswalk_links=crosswalk_links,
        risks_identified=risks,
        linchpin=linchpin,
        linchpin_is_top1=(linchpin == top1),
    )
