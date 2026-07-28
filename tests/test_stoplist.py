"""Non-substantive provisions are excluded from retrieval (but stay in the corpus)."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.ingest.base import Provision
from regulus.lookup import RegulusLookup
from regulus.stoplist import filter_substantive, is_substantive


def _corpus():
    return [
        Provision("eu_ai_act", "EU AI Act", "Article 113", "Entry into force and application",
                  "This Regulation shall enter into force on the twentieth day following its publication.", "u113"),
        Provision("eu_ai_act", "EU AI Act", "Article 10", "Data and data governance",
                  "Training data sets shall be examined for possible biases.", "u10"),
    ]


def test_is_substantive_and_split():
    assert not is_substantive("eu_ai_act", "Article 113")
    assert is_substantive("eu_ai_act", "Article 10")
    kept, removed = filter_substantive(_corpus())
    assert [p.provision_id for p in kept] == ["Article 10"]
    assert [p.provision_id for p in removed] == ["Article 113"]


def test_stoplisted_provision_not_retrieved():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.filter_non_substantive = True
    lookup = RegulusLookup(_corpus(), cfg)
    # even querying its own text must not return the procedural provision
    hits = [r.provision.provision_id for r in lookup.search("entry into force application publication", top_k=5)]
    assert "Article 113" not in hits


def test_filter_can_be_disabled():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.filter_non_substantive = False
    lookup = RegulusLookup(_corpus(), cfg)
    ids = set(lookup._by_id.keys())
    assert any(uid.endswith("article_113") for uid in ids)
