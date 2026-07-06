"""Offline lookup test over a tiny hand-made provision corpus (TF-IDF path)."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.ingest.base import Provision
from regulus.lookup import RegulusLookup


def _corpus():
    return [
        Provision("eu_ai_act", "EU AI Act", "Article 5", "Prohibited AI practices",
                  "Real-time remote biometric identification in publicly accessible spaces for law enforcement is prohibited.",
                  "https://x/#art_5"),
        Provision("nist_ai_rmf", "NIST AI RMF 1.0", "MEASURE 2.11", "Measure function",
                  "Fairness and bias are evaluated across demographic groups and results are documented.",
                  "https://x/nist"),
        Provision("eu_ai_act", "EU AI Act", "Article 15", "Accuracy, robustness and cybersecurity",
                  "High-risk AI systems shall achieve appropriate levels of accuracy and robustness.",
                  "https://x/#art_15"),
    ]


def test_lookup_returns_relevant_provision_with_provenance():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    lookup = RegulusLookup(_corpus(), cfg)

    results = lookup.search("we did not test our model for demographic bias", top_k=2)
    assert results
    top = results[0]
    assert top.provision.provision_id == "MEASURE 2.11"   # fairness provision wins
    assert top.provision.source_url                        # provenance present
    assert top.score > 0


def test_lookup_dedups_by_provision():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    lookup = RegulusLookup(_corpus(), cfg)
    results = lookup.search("biometric identification for law enforcement", top_k=3)
    ids = [r.provision.unique_id() for r in results]
    assert len(ids) == len(set(ids))  # no duplicate provisions
