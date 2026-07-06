"""Build the Regulus regulatory knowledge graph over ingested provisions.

Nodes: Framework, Provision, RiskCategory.
Edges:
  - CONTAINS   Framework  -> Provision           (from the corpus)
  - ADDRESSES  Provision  -> RiskCategory         (keyword-tagged, low-confidence)
  - CROSSWALK  Provision <-> Provision            (curated + cited)

The graph is a NetworkX graph with GKN-compatible node attributes (``node_type``,
``label``) so GKN's path explainer / retrievers can operate on it later.
"""
from __future__ import annotations

from typing import Dict, List

import networkx as nx

from .crosswalk import Crosswalk
from .ingest.base import Provision
from .risk import RISK_TAXONOMY, RiskCategory, tag_provision_risks
from .schema import EdgeType, NodeType


def _framework_node(framework_id: str) -> str:
    return f"framework::{framework_id}"


def _risk_node(risk_id: str) -> str:
    return f"risk::{risk_id}"


class RegulusGraphBuilder:
    def __init__(self, taxonomy: List[RiskCategory] | None = None) -> None:
        self.taxonomy = taxonomy or RISK_TAXONOMY

    def build(self, provisions: List[Provision], crosswalks: List[Crosswalk]) -> nx.Graph:
        graph = nx.Graph()
        provision_ids = {p.unique_id() for p in provisions}

        # Framework + Provision nodes, CONTAINS edges.
        for p in provisions:
            graph.add_node(
                p.unique_id(),
                node_type=NodeType.PROVISION.value,
                label=p.citation(),
                framework_id=p.framework_id,
                framework_name=p.framework_name,
                provision_id=p.provision_id,
                title=p.title,
                source_url=p.source_url,
                text=p.full_text(),
            )
            fw = _framework_node(p.framework_id)
            if fw not in graph:
                graph.add_node(fw, node_type=NodeType.FRAMEWORK.value, label=p.framework_name, framework_id=p.framework_id)
            graph.add_edge(fw, p.unique_id(), edge_type=EdgeType.CONTAINS.value)

        # RiskCategory nodes + ADDRESSES edges (keyword-derived, low confidence).
        for rc in self.taxonomy:
            graph.add_node(_risk_node(rc.risk_id), node_type=NodeType.RISK_CATEGORY.value, label=rc.name, description=rc.description)
        for p in provisions:
            for risk_id in tag_provision_risks(p, self.taxonomy):
                graph.add_edge(p.unique_id(), _risk_node(risk_id), edge_type=EdgeType.ADDRESSES.value, method="keyword", confidence=0.4)

        # CROSSWALK edges — curated + cited; skip any whose endpoints aren't loaded.
        added, skipped = 0, 0
        for cw in crosswalks:
            s, t = cw.source_uid(), cw.target_uid()
            if s in provision_ids and t in provision_ids:
                graph.add_edge(
                    s, t,
                    edge_type=EdgeType.CROSSWALK.value,
                    relation=cw.relation,
                    rationale=cw.rationale,
                    source=cw.source,
                )
                added += 1
            else:
                skipped += 1
        if skipped:
            print(f"[INFO] Crosswalks: {added} linked, {skipped} skipped (endpoint provision not in loaded corpus).")
        return graph


def graph_summary(graph: nx.Graph) -> Dict[str, int]:
    node_counts: Dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        node_counts[data.get("node_type", "Unknown")] = node_counts.get(data.get("node_type", "Unknown"), 0) + 1
    edge_counts: Dict[str, int] = {}
    for _, _, data in graph.edges(data=True):
        edge_counts[data.get("edge_type", "Unknown")] = edge_counts.get(data.get("edge_type", "Unknown"), 0) + 1
    return {**{f"node:{k}": v for k, v in node_counts.items()}, **{f"edge:{k}": v for k, v in edge_counts.items()}}
