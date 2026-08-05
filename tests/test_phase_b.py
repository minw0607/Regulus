"""Phase B: cross-framework eval, layer-aware retrieval, A/B dry-run, evidence paths."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.graph_eval import cross_framework_report
from regulus.graph_lookup import RegulusGraphLookup
from regulus.ingest.base import Provision
from regulus.lookup import RegulusLookup, framework_layer


def _corpus():
    # MEASURE 2.11 <-> Article 10 is a curated crosswalk in data/crosswalks/.
    return [
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups.", "u1"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training data sets shall be examined for possible biases.", "u2"),
        Provision("eu_ai_act", "EU AI Act", "Article 14", "Human oversight",
                  "High-risk AI systems shall be overseen by natural persons.", "u3"),
    ]


def test_cross_framework_report_graph_beats_flat_on_structural_case():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    gl = RegulusGraphLookup(_corpus(), cfg)
    # top_k=1: flat can only cover one of the two expected frameworks; the graph
    # must recover the crosswalked equivalent in the other framework.
    df = cross_framework_report(
        gl,
        eval_set=[("fairness and bias evaluated across demographic groups",
                   ["nist_ai_rmf::measure_2_11", "eu_ai_act::article_10"])],
        top_k=1,
    )
    row = df.iloc[0]
    assert row["flat recall"] < row["graph recall"] == 1.0
    assert row["graph fw found"] == 2
    assert list(df.iloc[-1])[0].startswith("AGGREGATE")


def test_layer_aware_retrieval_keeps_both_layers():
    provs = [
        Provision("owasp_llm_top10", "OWASP Top 10 for LLM (2025)", "LLM01", "Prompt Injection",
                  "Prompt injection attacks alter the model's behavior through crafted prompts.", "o1"),
        Provision("owasp_llm_top10", "OWASP Top 10 for LLM (2025)", "LLM07", "System Prompt Leakage",
                  "Prompt injection can expose the system prompt and alter model behavior.", "o2"),
        Provision("eu_ai_act", "EU AI Act", "Article 15", "Accuracy, robustness and cybersecurity",
                  "Systems shall be resilient to attacks such as prompt injection that alter behavior.", "e1"),
    ]
    query = "prompt injection attacks that alter model behavior"

    cfg_on = RegulusConfig(); cfg_on.retriever = "tfidf"; cfg_on.layer_aware = True
    layers_on = {framework_layer(r.provision.framework_id)
                 for r in RegulusLookup(provs, cfg_on).search(query, top_k=2)}

    cfg_off = RegulusConfig(); cfg_off.retriever = "tfidf"; cfg_off.layer_aware = False
    layers_off = {framework_layer(r.provision.framework_id)
                  for r in RegulusLookup(provs, cfg_off).search(query, top_k=2)}

    assert layers_on == {"regulatory", "threat"}
    # sanity: the quota is what made the difference (plain similarity is single-layer)
    assert layers_off == {"threat"}


def test_ab_dry_run_without_llm():
    from regulus.ab_eval import ab_compare, ab_report
    from regulus.interpret import RegulusInterpreter
    from regulus.system import RegulusSystem

    cfg = RegulusConfig(); cfg.retriever = "tfidf"; cfg.openai_api_key = ""
    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg))
    assert ab_compare(reg, "bias") is None
    assert ab_report(reg, ["bias"]).empty


def test_evidence_paths_render_with_signals():
    from regulus.assess import assess

    cfg = RegulusConfig(); cfg.retriever = "tfidf"; cfg.openai_api_key = ""
    gl = RegulusGraphLookup(_corpus(), cfg)
    a = assess(gl, "fairness and bias evaluated across groups", top_k=1, with_llm=False)
    paths = a.evidence_paths()
    assert paths
    # node —[signal]→ node structure, with the crosswalk rationale inside
    assert all("—[" in p and "]→" in p for p in paths)
