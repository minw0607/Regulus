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


def test_overview_renders_key_facts():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""

    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.interpret import RegulusInterpreter

    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg), standards=["nist_ai_rmf", "eu_ai_act"])
    md = reg.overview_markdown()
    for token in ("Regulatory data store", "Knowledge network", "Reproducibility", "Input", "Output"):
        assert token in md
    assert reg.overview() is None  # renders; must not return the raw string (notebook Out[] echo)


def test_assess_is_deterministic_core_and_reproducible():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""  # dry run — deterministic core only, no LLM

    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.interpret import RegulusInterpreter

    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg, target_system="A credit model"),
                        target_system="A credit model")

    a1 = reg.assess("model not tested for demographic bias", top_k=2, render=False)
    a2 = reg.assess("model not tested for demographic bias", top_k=2, render=False)

    # deterministic core is identical across runs
    assert [p.citation for p in a1.primary] == [p.citation for p in a2.primary]
    assert a1.risks == a2.risks
    assert [p.citation for p in a1.priority] == [p.citation for p in a2.priority]
    assert a1.to_markdown() == a2.to_markdown()  # dry run: no LLM variation at all
    # structure: at least one applicable provision, LLM section labeled as unavailable
    assert a1.primary
    assert a1.interpretation is not None and a1.interpretation.answer_markdown is None
    # tabular views + priority present
    assert list(a1.risk_table().columns) == ["risk", "relevant provisions (standards)", "suggested control / mitigant"]
    assert a1.priority and a1.linchpin is not None


def test_assess_export_writes_files(tmp_path):
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""

    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.interpret import RegulusInterpreter

    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg), target_system="A credit model")

    a = reg.assess("bias not tested", top_k=2, render=False)
    folder = reg.export(a, out_dir=str(tmp_path))
    assert (folder / "assessment.md").exists()
    assert (folder / "assessment.json").exists()
    assert (folder / "risks.csv").exists()

    import json
    data = json.loads((folder / "assessment.json").read_text())
    assert set(data) >= {"scenario", "risks", "primary_provisions", "priority", "graph_reach", "controls"}


def test_compare_rag_and_coverage_shapes():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""

    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.interpret import RegulusInterpreter

    provs = _corpus()
    gl = RegulusGraphLookup(provs, cfg)
    reg = RegulusSystem(cfg, provs, gl, RegulusInterpreter(gl, cfg))

    cmp = reg.compare_rag("bias fairness data", render=False)
    assert list(cmp.columns) == ["dimension", "flat RAG (similarity only)", "Regulus GraphRAG"]
    cov = reg.coverage({"bias": "bias fairness data governance"})
    assert list(cov.columns) == ["scenario", "top provision", "frameworks hit", "risks identified", "risk categories"]
