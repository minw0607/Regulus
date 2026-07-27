"""Offline tests for the graph-intelligence layer (the GKN value-add)."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.controls import CONTROL_LIBRARY, control_for
from regulus.graph_intelligence import graph_expand, prioritize, rag_vs_graph
from regulus.graph_lookup import RegulusGraphLookup
from regulus.ingest.base import Provision


def _corpus():
    # MEASURE 2.11 <-> Article 10 is a curated crosswalk in data/crosswalks/.
    return [
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups.", "u1"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training data sets shall be examined for possible biases.", "u2"),
    ]


def _gl():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    return RegulusGraphLookup(_corpus(), cfg)


def test_graph_expand_surfaces_crosswalked_provision_not_retrieved():
    gl = _gl()
    results = gl.search("Fairness and bias are evaluated across demographic groups", top_k=1)
    assert len(results) == 1  # only the NIST provision retrieved
    reach = graph_expand(gl, results, max_hops=2)
    # the graph reaches the crosswalked EU provision that similarity did not return
    assert any("Article 10" in r.citation for r in reach)
    hit = next(r for r in reach if "Article 10" in r.citation)
    assert hit.hops >= 1 and len(hit.path) >= 2


def test_prioritize_ranks_by_leverage():
    gl = _gl()
    results = gl.search("bias fairness data governance training", top_k=2)
    items = prioritize(gl, results)
    assert items
    # sorted by priority descending
    assert all(items[i].priority >= items[i + 1].priority for i in range(len(items) - 1))
    # a crosswalk-connected provision registers leverage
    assert any(it.leverage > 0 for it in items)


def test_rag_vs_graph_expands_framework_coverage():
    gl = _gl()
    c = rag_vs_graph(gl, "Fairness and bias are evaluated across demographic groups", top_k=1)
    assert c.flat_provisions == 1
    assert len(c.graph_frameworks) >= len(c.flat_frameworks)
    assert c.graph_extra_provisions >= 1
    assert c.linchpin


def test_summarize_neighborhood_is_deterministic_and_structured():
    from regulus.graph_intelligence import summarize_neighborhood

    gl = _gl()
    scenario = "training data not examined for bias; fairness across groups not tested"
    s1 = summarize_neighborhood(gl, scenario, top_k=2)
    s2 = summarize_neighborhood(gl, scenario, top_k=2)
    assert s1.direct_hits and s1.frameworks_in_view
    assert s1.to_markdown() == s2.to_markdown()  # fully reproducible template
    md = s1.to_markdown()
    for token in ("Direct hits", "Cross-framework reach", "Risks in play", "Address first"):
        assert token in md


def test_describe_neighborhood_falls_back_to_template_without_llm():
    from regulus.graph_intelligence import summarize_neighborhood
    from regulus.interpret import RegulusInterpreter

    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""  # no LLM
    gl = RegulusGraphLookup(_corpus(), cfg)
    interp = RegulusInterpreter(gl, cfg)
    summary = summarize_neighborhood(gl, "bias fairness data governance", top_k=2)
    narrative, reason = interp.describe_neighborhood(summary)
    assert narrative is None and reason  # signals caller to use summary.to_markdown()


def test_control_library_covers_all_risks():
    from regulus.risk import RISK_TAXONOMY

    for rc in RISK_TAXONOMY:
        assert rc.risk_id in CONTROL_LIBRARY
    # unknown risk id returns a generic placeholder, not an error
    assert control_for("does_not_exist").objective
