"""Crosswalk-aware lookup: issue -> applicable provisions, each annotated with the
risks it addresses and its cited cross-framework references.

This is the Phase-2 payoff. It composes the Phase-1 retrieval baseline with the
regulatory knowledge graph: retrieve the applicable provisions, then walk the
graph's CROSSWALK edges to surface equivalent guidance in other frameworks (with
the mapping's citation) and ADDRESSES edges to name the risks involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import networkx as nx

from .config import RegulusConfig
from .crosswalk import load_crosswalks
from .graph import RegulusGraphBuilder
from .ingest.base import Provision
from .lookup import RegulusLookup
from .schema import EdgeType, NodeType


@dataclass
class CrossReference:
    provision: Provision
    relation: str
    rationale: str
    source: str  # citation for the crosswalk mapping

    def line(self) -> str:
        return f"{self.provision.citation()}  ({self.relation}; source: {self.source})"


@dataclass
class GraphLookupResult:
    provision: Provision
    score: float
    snippet: str
    risks: List[str] = field(default_factory=list)
    crosswalks: List[CrossReference] = field(default_factory=list)


class RegulusGraphLookup:
    def __init__(self, provisions: List[Provision], config: RegulusConfig | None = None) -> None:
        self.config = config or RegulusConfig()
        self.provisions = provisions
        self._by_uid = {p.unique_id(): p for p in provisions}
        self.lookup = RegulusLookup(provisions, self.config)
        self.graph = RegulusGraphBuilder().build(provisions, load_crosswalks())

    def search(self, issue: str, top_k: int | None = None) -> List[GraphLookupResult]:
        base_results = self.lookup.search(issue, top_k=top_k)
        enriched: List[GraphLookupResult] = []
        for r in base_results:
            uid = r.provision.unique_id()
            enriched.append(
                GraphLookupResult(
                    provision=r.provision,
                    score=r.score,
                    snippet=r.snippet,
                    risks=self._risks_for(uid),
                    crosswalks=self._crosswalks_for(uid),
                )
            )
        return enriched

    def _risks_for(self, uid: str) -> List[str]:
        if uid not in self.graph:
            return []
        names = []
        for neighbor in self.graph.neighbors(uid):
            edge = self.graph.edges[uid, neighbor]
            if edge.get("edge_type") == EdgeType.ADDRESSES.value:
                names.append(self.graph.nodes[neighbor].get("label", neighbor))
        return sorted(names)

    def _crosswalks_for(self, uid: str) -> List[CrossReference]:
        if uid not in self.graph:
            return []
        refs: List[CrossReference] = []
        for neighbor in self.graph.neighbors(uid):
            edge = self.graph.edges[uid, neighbor]
            if edge.get("edge_type") != EdgeType.CROSSWALK.value:
                continue
            provision = self._by_uid.get(neighbor)
            if provision is None:
                continue
            refs.append(
                CrossReference(
                    provision=provision,
                    relation=edge.get("relation", "related"),
                    rationale=edge.get("rationale", ""),
                    source=edge.get("source", ""),
                )
            )
        return refs
