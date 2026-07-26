"""Offline test for the RegulusSystem facade (dry-run, TF-IDF)."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.ingest.base import Provision
from regulus.system import RegulusSystem


def _corpus():
    return [
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups.", "https://x/nist"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training data sets shall be examined for possible biases.", "https://x/#art_10"),
    ]


def test_system_launch_and_facade():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""  # dry run

    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.interpret import RegulusInterpreter

    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg, target_system="A test model"),
                        standards=["nist_ai_rmf", "eu_ai_act"], target_system="A test model")

    info = reg.info()
    assert set(info["property"]) >= {"provisions", "retriever", "LLM interpretation", "target system"}
    assert not reg.lookup("model not tested for bias", top_k=2).empty
    result = reg.analyze("model not tested for bias", top_k=2)
    assert result.answer_markdown is None  # dry run
    assert result.context and result.citations
