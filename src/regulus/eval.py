"""A small retrieval eval — so data-store changes (chunking, embeddings) are measured.

Each case maps a plain-language issue to the provision(s) that *should* be
retrieved (by their unique id). This is a **sanity/regression set**, hand-curated
and deliberately small — not an authoritative benchmark. Extend it as coverage
grows.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import pandas as pd

# (issue, [expected provision unique_ids])
EVAL_SET: List[Tuple[str, List[str]]] = [
    ("Real-time facial recognition in public spaces for law enforcement", ["eu_ai_act::article_5"]),
    ("Our credit model was deployed without testing for demographic bias", ["nist_ai_rmf::measure_2_11", "eu_ai_act::article_10"]),
    ("No post-deployment monitoring of a high-risk AI system", ["eu_ai_act::article_72", "nist_ai_rmf::manage_4_1"]),
    ("Users are not told they are interacting with an AI system", ["eu_ai_act::article_50"]),
    ("No human oversight of the model's automated decisions", ["eu_ai_act::article_14"]),
    ("The high-risk system was not validated for accuracy and robustness", ["eu_ai_act::article_15"]),
    ("No logging or records of the AI system's operation", ["eu_ai_act::article_12"]),
    ("There is no risk management system for our high-risk AI", ["eu_ai_act::article_9"]),
    ("We provide no instructions for use or transparency information to deployers", ["eu_ai_act::article_13"]),
    ("No fundamental rights impact assessment was performed", ["eu_ai_act::article_27"]),
    ("Training data was not examined for bias or properly governed", ["eu_ai_act::article_10", "iso_42001::annex_a_7"]),
    ("No technical documentation of the high-risk system", ["eu_ai_act::article_11"]),
]


def retrieval_report(graph_lookup, eval_set: Sequence = None, top_k: int = 5) -> pd.DataFrame:
    """Return a per-case table (hit / recall@k / MRR / top-1) with an AGGREGATE row.

    ``graph_lookup`` is any object with ``.search(issue, top_k)`` returning results
    that expose ``.provision.unique_id()`` (RegulusLookup or RegulusGraphLookup)."""
    eval_set = eval_set or EVAL_SET
    rows = []
    for issue, expected in eval_set:
        expected_set = set(expected)
        results = graph_lookup.search(issue, top_k=top_k)
        retrieved = [r.provision.unique_id() for r in results]
        retrieved_set = set(retrieved)

        hit = float(bool(retrieved_set & expected_set))
        recall = len(retrieved_set & expected_set) / len(expected_set) if expected_set else 0.0
        mrr = 0.0
        for rank, uid in enumerate(retrieved, 1):
            if uid in expected_set:
                mrr = 1.0 / rank
                break
        top1 = results[0].provision.citation() if results else "—"
        rows.append({"issue": issue[:60], "hit": hit, "recall@k": round(recall, 2), "mrr": round(mrr, 2), "top-1": top1})

    df = pd.DataFrame(rows)
    if not df.empty:
        agg = {
            "issue": f"AGGREGATE (n={len(df)}, k={top_k})",
            "hit": round(df["hit"].mean(), 3),
            "recall@k": round(df["recall@k"].mean(), 3),
            "mrr": round(df["mrr"].mean(), 3),
            "top-1": "",
        }
        df = pd.concat([df, pd.DataFrame([agg])], ignore_index=True)
    return df
