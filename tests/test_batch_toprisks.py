"""Tests for top-N risks, batch (multi-finding) assessment, and consistency check."""
from __future__ import annotations

from regulus.assess import assess
from regulus.batch import assess_batch, consistency_check
from regulus.config import RegulusConfig
from regulus.graph_lookup import RegulusGraphLookup
from regulus.ingest.base import Provision


def _corpus():
    return [
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups.", "u1"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training data sets shall be examined for possible biases and fairness.", "u2"),
        Provision("eu_ai_act", "EU AI Act", "Article 15", "Accuracy, robustness and cybersecurity",
                  "Systems shall be accurate, robust and secure against attacks.", "u3"),
    ]


def _gl():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    return RegulusGraphLookup(_corpus(), cfg)


def test_top_risks_ranked_and_explainable():
    a = assess(_gl(), "bias and fairness across demographic groups in training data", top_k=3, with_llm=False)
    df = a.top_risks(3)
    assert not df.empty
    assert list(df.columns) == ["rank", "risk", "score", "driving provisions (relevance)", "why"]
    assert list(df["rank"]) == list(range(1, len(df) + 1))
    assert (df["score"].diff().dropna() <= 0).all()          # descending
    assert df.iloc[0]["why"] and "Control objective" in df.iloc[0]["why"]
    # deterministic
    assert a.top_risks(3).equals(df)


def test_batch_matrix_systemic_and_priority():
    gl = _gl()
    findings = {
        "F1 bias": "bias and fairness across demographic groups",
        "F2 data": "training data examined for possible biases",
    }
    batch = assess_batch(gl, findings, target_system="test model", top_k=2)
    m = batch.risk_matrix()
    assert list(m.index) == ["F1 bias", "F2 data"]
    assert m.shape[1] >= 1
    # both findings retrieve the bias-related provisions -> systemic anchors exist
    sys_df = batch.systemic_provisions()
    assert not sys_df.empty
    assert (sys_df["findings implicated"] >= 2).all()
    cp = batch.consolidated_priority()
    assert not cp.empty
    assert (cp["review priority"].diff().dropna() <= 0).all()
    md = batch.to_markdown()
    for token in ("Findings × risks", "Systemic anchors", "address-first"):
        assert token in md


def test_consistency_check_identical_cores():
    df = consistency_check(_gl(), "bias and fairness evaluation", runs=3, top_k=2)
    assert len(df) == 3
    assert df["identical to run 1"].all()
    assert df["deterministic core hash"].nunique() == 1
