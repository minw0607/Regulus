"""Cross-framework evaluation — the fair, outcome-based flat-RAG-vs-graph test.

The knowledge network is not claimed to help every lookup. Its claim is narrower
and testable: for questions whose full answer **spans frameworks** (what the law
requires + how other standards express it + which threat/control knowledge
applies), following cited relationships recovers provisions that similarity
alone misses. This module measures exactly that:

- Each eval case maps a scenario to an expected provision set that **spans at
  least two frameworks** (regulation ↔ regulation, or regulation ↔ threat layer).
- **Flat RAG** gets a genuine chance: it retrieves over the *whole* corpus with
  the same retriever and the same k — it may find the equivalents by similarity.
- **Graph** = the same retrieval **plus crosswalk expansion** (multi-hop, cited).
- Metric: *cross-framework recall@k* — how much of the expected set each method
  covers — plus how many expected frameworks each reaches.

Same scenario + same store + same retriever ⇒ identical table, every run.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import pandas as pd

from .graph_intelligence import graph_expand

# (scenario, expected provision uids — every case spans >= 2 frameworks)
CROSS_FRAMEWORK_EVAL: List[Tuple[str, List[str]]] = [
    ("Our credit model was deployed without testing for demographic bias and its training data was never examined",
     ["eu_ai_act::article_10", "nist_ai_rmf::measure_2_11", "iso_42001::annex_a_7"]),
    ("Users can inject instructions through prompts or retrieved content to alter our LLM's behaviour",
     ["owasp_llm_top10::llm01", "mitre_atlas::aml_t0051", "nist_ai_rmf::measure_2_7"]),
    ("An attacker could poison our training data or fine-tuning corpus (data poisoning)",
     ["owasp_llm_top10::llm04", "mitre_atlas::aml_t0020", "eu_ai_act::article_15"]),
    ("There is no post-deployment monitoring of our high-risk AI system",
     ["eu_ai_act::article_72", "nist_ai_rmf::manage_4_1"]),
    ("Our AI agent takes high-impact automated actions with no human review or approval",
     ["eu_ai_act::article_14", "mitre_atlas::aml_m0029", "owasp_llm_top10::llm06"]),
    ("We give users no transparency about the AI system or how to use it",
     ["eu_ai_act::article_13", "nist_ai_rmf::measure_2_8", "oecd_ai::principle_1_3"]),
    ("There is no AI risk management process across the lifecycle",
     ["eu_ai_act::article_9", "nist_ai_rmf::govern_1_1", "iso_42001::clause_6"]),
    ("The system was never tested for robustness, security, or resilience to attack",
     ["eu_ai_act::article_15", "nist_ai_rmf::measure_2_7", "oecd_ai::principle_1_4"]),
    ("The chatbot can be manipulated into revealing its hidden system prompt",
     ["owasp_llm_top10::llm07", "mitre_atlas::aml_t0056"]),
    ("A compromised third-party model or component could enter our AI supply chain",
     ["owasp_llm_top10::llm03", "mitre_atlas::aml_t0010", "eu_ai_act::article_25"]),
]


def _framework_of(uid: str) -> str:
    return uid.split("::", 1)[0]


def cross_framework_report(
    graph_lookup, eval_set: Sequence = None, top_k: int = 5, max_hops: int = 2
) -> pd.DataFrame:
    """Per-case coverage of the expected cross-framework set: flat vs flat+graph."""
    eval_set = eval_set or CROSS_FRAMEWORK_EVAL
    rows = []
    for scenario, expected in eval_set:
        expected_set = set(expected)
        expected_fws = {_framework_of(u) for u in expected_set}

        results = graph_lookup.search(scenario, top_k=top_k)
        flat_uids = {r.provision.unique_id() for r in results}
        reach = graph_expand(graph_lookup, results, max_hops=max_hops)
        graph_uids = flat_uids | {r.uid for r in reach}

        flat_cov = len(flat_uids & expected_set) / len(expected_set)
        graph_cov = len(graph_uids & expected_set) / len(expected_set)
        flat_fws = {_framework_of(u) for u in flat_uids & expected_set}
        graph_fws = {_framework_of(u) for u in graph_uids & expected_set}

        rows.append({
            "scenario": scenario[:58],
            "expected frameworks": len(expected_fws),
            "flat recall": round(flat_cov, 2),
            "graph recall": round(graph_cov, 2),
            "Δ recall": round(graph_cov - flat_cov, 2),
            "flat fw found": len(flat_fws),
            "graph fw found": len(graph_fws),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        agg = {
            "scenario": f"AGGREGATE (n={len(df)}, k={top_k}, hops≤{max_hops})",
            "expected frameworks": round(df["expected frameworks"].mean(), 1),
            "flat recall": round(df["flat recall"].mean(), 3),
            "graph recall": round(df["graph recall"].mean(), 3),
            "Δ recall": round((df["graph recall"] - df["flat recall"]).mean(), 3),
            "flat fw found": round(df["flat fw found"].mean(), 1),
            "graph fw found": round(df["graph fw found"].mean(), 1),
        }
        df = pd.concat([df, pd.DataFrame([agg])], ignore_index=True)
    return df
