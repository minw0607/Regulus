"""Non-substantive provisions to exclude from retrieval.

Some provisions are procedural or administrative — they describe the regulation's
own mechanics (definitions, scope, delegated-act and committee procedure,
amendments to other laws, transitional rules, entry into force) and impose no
governance obligation. They are legitimate parts of the corpus but they are
*noise* as retrieval hits: a risk scenario should never map to "Entry into force
and application". Left in, they surface as spurious direct hits (e.g. EU AI Act
Article 113) and clutter the risk graph.

This is a small, transparent, **curated** stoplist keyed by ``framework_id`` →
provision ids. Retrieval skips these; the graph still contains them (so corpus
counts stay honest), they simply never surface as results. Toggle with
``RegulusConfig.filter_non_substantive``.
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

# framework_id -> provision_ids that carry no substantive governance obligation.
NON_SUBSTANTIVE: Dict[str, Set[str]] = {
    "eu_ai_act": {
        "Article 1",    # Subject matter
        "Article 2",    # Scope
        "Article 3",    # Definitions
        "Article 7",    # Amendments to Annex III (delegated power)
        "Article 97",   # Exercise of the delegation
        "Article 98",   # Committee procedure
        "Article 102",  # Amendment to Regulation (EC) No 300/2008
        "Article 103",  # Amendment to Regulation (EU) No 167/2013
        "Article 104",  # Amendment to Regulation (EU) No 168/2013
        "Article 105",  # Amendment to Directive 2014/90/EU
        "Article 106",  # Amendment to Directive (EU) 2016/797
        "Article 107",  # Amendment to Regulation (EU) 2018/858
        "Article 108",  # Amendments to Regulation (EU) 2018/1139
        "Article 109",  # Amendment to Regulation (EU) 2019/2144
        "Article 110",  # Amendment to Directive (EU) 2020/1828
        "Article 111",  # Transitional (systems already on the market)
        "Article 112",  # Evaluation and review
        "Article 113",  # Entry into force and application
    },
    # ISO/IEC 42001 front matter (structure snapshot): Scope / Normative references
    # / Terms carry no requirement (the normative clauses are 4–10 + Annex A).
    "iso_42001": {"Clause 1", "Clause 2", "Clause 3"},
}


def is_substantive(framework_id: str, provision_id: str) -> bool:
    return provision_id not in NON_SUBSTANTIVE.get(framework_id, set())


def filter_substantive(provisions: List) -> Tuple[List, List]:
    """Split provisions into (kept substantive, removed non-substantive)."""
    kept, removed = [], []
    for p in provisions:
        (kept if is_substantive(p.framework_id, p.provision_id) else removed).append(p)
    return kept, removed
