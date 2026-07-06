"""Offline tests for the Phase-2 crosswalk graph."""
from __future__ import annotations

from pathlib import Path

from regulus.config import RegulusConfig
from regulus.crosswalk import Crosswalk, load_crosswalks
from regulus.graph import RegulusGraphBuilder, graph_summary
from regulus.graph_lookup import RegulusGraphLookup
from regulus.ingest.base import Provision
from regulus.risk import tag_provision_risks
from regulus.schema import EdgeType, NodeType


def _corpus():
    return [
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups; discrimination is documented.",
                  "https://x/nist"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training, validation and testing data sets shall be examined for possible biases.",
                  "https://x/#art_10"),
        Provision("eu_ai_act", "EU AI Act", "Article 99", "Penalties",
                  "Member States shall lay down penalties applicable to infringements.",
                  "https://x/#art_99"),
    ]


def test_curated_crosswalks_load_and_are_cited():
    cws = load_crosswalks()
    assert cws, "seed crosswalks should load"
    assert all(cw.source for cw in cws), "every crosswalk must carry a source/citation"
    assert all(cw.source_framework != cw.target_framework for cw in cws), "crosswalks are cross-framework"


def test_graph_builder_nodes_and_cited_crosswalk_edge():
    provs = _corpus()
    cw = Crosswalk("nist_ai_rmf", "MEASURE 2.11", "eu_ai_act", "Article 10",
                   "related", "fairness <-> data governance", "curated seed")
    # include a crosswalk whose endpoint is absent -> must be skipped
    cw_missing = Crosswalk("nist_ai_rmf", "MEASURE 2.11", "eu_ai_act", "Article 999", "related", "", "x")
    graph = RegulusGraphBuilder().build(provs, [cw, cw_missing])

    summary = graph_summary(graph)
    assert summary.get("node:" + NodeType.FRAMEWORK.value) == 2
    assert summary.get("node:" + NodeType.PROVISION.value) == 3
    assert summary.get("edge:" + EdgeType.CROSSWALK.value) == 1  # missing-endpoint skipped

    s = provs[0].unique_id()
    t = provs[1].unique_id()
    edge = graph.edges[s, t]
    assert edge["edge_type"] == EdgeType.CROSSWALK.value
    assert edge["source"] == "curated seed"


def test_risk_tagger_ranks_and_caps():
    provs = _corpus()
    tags = tag_provision_risks(provs[0])          # fairness-heavy text
    assert "fair_bias_managed" in tags
    assert len(tags) <= 3


def test_graph_lookup_surfaces_cited_crosswalk():
    provs = _corpus()
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    # point the graph at our seed table by monkeypatching the corpus crosswalk
    gl = RegulusGraphLookup(provs, cfg)
    # force a known crosswalk into the graph for a deterministic assertion
    s, t = provs[0].unique_id(), provs[1].unique_id()
    gl.graph.add_edge(s, t, edge_type=EdgeType.CROSSWALK.value, relation="related", rationale="", source="curated seed")

    results = gl.search("model not tested for demographic bias", top_k=2)
    assert results
    top = results[0]
    assert top.provision.provision_id == "MEASURE 2.11"
    assert any(cx.provision.provision_id == "Article 10" and cx.source for cx in top.crosswalks)
