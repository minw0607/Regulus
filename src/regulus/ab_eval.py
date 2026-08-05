"""Blind A/B: does graph context produce better answers than flat context?

Feature counts can be argued with; answer quality is the outcome that matters.
For a scenario, we generate two assessments with the SAME LLM at temperature 0:

- **flat context** — the top-k retrieved provision texts only (what a plain RAG
  pipeline would send);
- **graph context** — the same provisions *plus their typed relationships*
  (risks, cited crosswalks with rationales) exactly as Regulus sends them.

A judge (same model, temperature 0) scores both on a fixed rubric — grounding,
cross-framework coverage, actionability, depth — **blind**: answers are labeled
"Answer 1/2" with the order decided by a hash of the scenario, so the judge
cannot know which method produced which. Scores are unblinded afterwards.

LLM required (generation + judging); without a key this returns a dry-run note.
The verdicts are LLM-judged and should be read as evidence, not proof — the
deterministic cross-framework recall eval (graph_eval.py) is the harder number.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import List, Optional

import pandas as pd

_GEN_SYSTEM = """You are an AI-governance and model-risk assistant. Using ONLY the provisions in the \
CONTEXT, produce a concise assessment of the scenario: the risks, why each cited provision applies, \
how the provisions relate across frameworks (only if the context shows relationships), and concrete \
recommended mitigants grounded in cited provisions. Cite every claim. Never invent a provision."""

_GEN_TEMPLATE = """SCENARIO:
{scenario}

CONTEXT:
{context}

Write the assessment in Markdown (max ~500 words)."""

_JUDGE_SYSTEM = """You are a strict evaluator of AI-governance assessments. Score each answer on four \
criteria, 1-5 each (5 = excellent):
- grounding: every claim cited to provisions that plausibly exist in the answer's context; no invented obligations
- cross_framework: does it connect requirements across multiple frameworks/standards coherently?
- actionability: are the mitigants concrete, prioritized, and tied to cited provisions?
- depth: does it explain root causes and relationships, beyond listing documents?

Return ONLY JSON: {"answer1": {"grounding": n, "cross_framework": n, "actionability": n, "depth": n},
"answer2": {...}, "better_overall": 1 or 2, "reason": "<one sentence>"}"""

_JUDGE_TEMPLATE = """SCENARIO:
{scenario}

ANSWER 1:
{answer1}

ANSWER 2:
{answer2}

Score both answers. JSON only."""


def _flat_context(results) -> str:
    """What plain RAG would send: provision texts, no relationships."""
    blocks = []
    for i, r in enumerate(results, 1):
        blocks.append(f"[{i}] {r.provision.citation()}  (source: {r.provision.source_url})\n"
                      f"    text: {r.snippet.strip()[:400]}")
    return "\n\n".join(blocks) if blocks else "(no provisions retrieved)"


def _parse_judge_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def ab_compare(system, scenario: str, top_k: int = 5, max_tokens: int = 1200) -> Optional[dict]:
    """Run one blind A/B for a scenario. Returns a dict of scores, or None with a
    printed note when no LLM is configured."""
    interp = system.interpreter
    reason = interp._llm_unavailable_reason()
    if reason is not None:
        print(f"[ab] skipped — no LLM available ({reason}).")
        return None

    results = system.graph_lookup.search(scenario, top_k=top_k)
    flat_ctx = _flat_context(results)
    graph_ctx, _ = interp.build_context_from_results(results)

    client = interp._build_client()

    def _gen(context: str) -> str:
        messages = [
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": _GEN_TEMPLATE.format(scenario=scenario, context=context)},
        ]
        return interp._chat_create(client, messages, temperature=0.0, max_tokens=max_tokens).choices[0].message.content

    flat_answer = _gen(flat_ctx)
    graph_answer = _gen(graph_ctx)

    # Blind: assignment order decided by a stable hash of the scenario.
    flat_first = int(hashlib.sha256(scenario.encode()).hexdigest(), 16) % 2 == 0
    a1, a2 = (flat_answer, graph_answer) if flat_first else (graph_answer, flat_answer)

    judge_messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": _JUDGE_TEMPLATE.format(scenario=scenario, answer1=a1, answer2=a2)},
    ]
    verdict_text = interp._chat_create(client, judge_messages, temperature=0.0, max_tokens=600).choices[0].message.content
    verdict = _parse_judge_json(verdict_text)
    if verdict is None:
        print("[ab] judge returned unparseable output; skipping case.")
        return None

    # Unblind.
    key_flat = "answer1" if flat_first else "answer2"
    key_graph = "answer2" if flat_first else "answer1"
    better = verdict.get("better_overall")
    winner = "graph" if (better == (2 if flat_first else 1)) else "flat" if better in (1, 2) else "?"
    return {
        "scenario": scenario[:58],
        "flat": verdict.get(key_flat, {}),
        "graph": verdict.get(key_graph, {}),
        "winner": winner,
        "judge_reason": verdict.get("reason", ""),
    }


def ab_report(system, scenarios: List[str], top_k: int = 5) -> pd.DataFrame:
    """Blind A/B over several scenarios; one row per case + aggregate means."""
    rows = []
    for s in scenarios:
        out = ab_compare(system, s, top_k=top_k)
        if out is None:
            continue
        f, g = out["flat"], out["graph"]
        rows.append({
            "scenario": out["scenario"],
            "flat total": sum(v for v in f.values() if isinstance(v, (int, float))),
            "graph total": sum(v for v in g.values() if isinstance(v, (int, float))),
            "flat cross-fw": f.get("cross_framework"),
            "graph cross-fw": g.get("cross_framework"),
            "winner (blind judge)": out["winner"],
            "judge reason": out["judge_reason"][:90],
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        agg = {
            "scenario": f"AGGREGATE (n={len(df)})",
            "flat total": round(df["flat total"].mean(), 2),
            "graph total": round(df["graph total"].mean(), 2),
            "flat cross-fw": round(pd.to_numeric(df["flat cross-fw"]).mean(), 2),
            "graph cross-fw": round(pd.to_numeric(df["graph cross-fw"]).mean(), 2),
            "winner (blind judge)": f"graph {int((df['winner (blind judge)']=='graph').sum())}"
                                    f" / flat {int((df['winner (blind judge)']=='flat').sum())}",
            "judge reason": "",
        }
        df = pd.concat([df, pd.DataFrame([agg])], ignore_index=True)
    return df
