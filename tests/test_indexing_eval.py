"""Offline tests for provision-aware indexing and the retrieval eval."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.eval import retrieval_report
from regulus.graph_lookup import RegulusGraphLookup
from regulus.indexing import build_units
from regulus.ingest.base import Provision


def _corpus():
    long_text = " ".join(f"This is normative sentence number {i} about data governance and bias." for i in range(40))
    return [
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance", long_text, "https://x/#art_10"),
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups.", "https://x/nist"),
    ]


def test_build_units_are_provision_scoped_and_headed():
    provs = _corpus()
    units = build_units(provs, max_chars=300)
    # long provision splits into multiple sentence-bounded units; short one stays whole
    a10 = [u for u in units if u.doc_id == "eu_ai_act::article_10"]
    assert len(a10) > 1
    # every unit carries the header (framework + provision id) and maps to its provision
    assert all(u.text.startswith("EU AI Act — Article 10") for u in a10)
    assert all(u.doc_id == "eu_ai_act::article_10" for u in a10)


def test_retrieval_report_shape():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    gl = RegulusGraphLookup(_corpus(), cfg)
    df = retrieval_report(gl, eval_set=[("bias and fairness evaluation across groups", ["nist_ai_rmf::measure_2_11"])], top_k=3)
    assert list(df.columns) == ["issue", "hit", "recall@k", "mrr", "top-1"]
    assert df.iloc[-1]["issue"].startswith("AGGREGATE")
