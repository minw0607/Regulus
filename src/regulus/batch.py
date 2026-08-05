"""Multi-run assessment — from one finding to a whole review.

In practice a review of an AI system is not one lookup: a validation exam or
audit raises **several findings**, each assessed separately, and the reviewer
then needs the consolidated picture. This module provides that:

- :func:`assess_batch` runs the (deterministic) assessment for each finding and
  returns a :class:`BatchAssessment` with consolidated views:

  * ``risk_matrix()`` — findings × risks (how many retrieved provisions address
    each risk per finding) — the basis of the review heatmap;
  * ``systemic_provisions()`` — provisions implicated by **two or more**
    findings: recurring anchors that indicate a *systemic* gap, not a one-off;
  * ``consolidated_priority()`` — the address-first ranking across the whole
    review (a provision that is the linchpin of several findings outranks a
    linchpin of one).

- :func:`consistency_check` re-runs the same scenario N times and verifies the
  deterministic core is **identical** on every run (hash comparison) — the
  multiple-run reproducibility test, made visible.

Everything here is code-computed from retrieval + the graph; no LLM calls, so a
batch is fast and its tables are byte-identical across runs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .assess import Assessment, assess


@dataclass
class BatchAssessment:
    target_system: str
    assessments: Dict[str, Assessment]   # finding name -> assessment

    def risk_matrix(self) -> pd.DataFrame:
        """Findings × risks: #retrieved provisions addressing each risk per finding."""
        all_risks: List[str] = sorted({r for a in self.assessments.values() for r, _ in a.risks})
        rows = []
        for name, a in self.assessments.items():
            counts = {risk: len(provs) for risk, provs in a.risks}
            rows.append({"finding": name, **{r: counts.get(r, 0) for r in all_risks}})
        return pd.DataFrame(rows).set_index("finding")

    def systemic_provisions(self, min_findings: int = 2) -> pd.DataFrame:
        """Provisions implicated by >= min_findings findings — systemic anchors."""
        seen: Dict[str, List[str]] = {}
        for name, a in self.assessments.items():
            for p in a.primary:
                seen.setdefault(p.citation, [])
                if name not in seen[p.citation]:
                    seen[p.citation].append(name)
        rows = [
            {"provision": cit, "findings implicated": len(names), "findings": ", ".join(names)}
            for cit, names in seen.items() if len(names) >= min_findings
        ]
        rows.sort(key=lambda r: (-r["findings implicated"], r["provision"]))
        return pd.DataFrame(rows, columns=["provision", "findings implicated", "findings"])

    def consolidated_priority(self, top_n: int = 10) -> pd.DataFrame:
        """Address-first ranking for the whole review: provisions scored by how many
        findings they appear in and their mean per-finding priority score."""
        acc: Dict[str, dict] = {}
        for name, a in self.assessments.items():
            for item in a.priority:
                d = acc.setdefault(item.citation, {"provision": item.citation, "findings": [], "scores": []})
                if name not in d["findings"]:
                    d["findings"].append(name)
                d["scores"].append(item.priority)
        rows = []
        for d in acc.values():
            mean_score = sum(d["scores"]) / len(d["scores"])
            rows.append({
                "provision": d["provision"],
                "findings implicated": len(d["findings"]),
                "mean priority": round(mean_score, 3),
                "review priority": round(len(d["findings"]) * mean_score, 3),
            })
        rows.sort(key=lambda r: (-r["review priority"], r["provision"]))
        for i, r in enumerate(rows[:top_n], 1):
            r["rank"] = i
        df = pd.DataFrame(rows[:top_n])
        return df[["rank", "provision", "findings implicated", "mean priority", "review priority"]] if not df.empty else df

    def to_markdown(self) -> str:
        from .assess import _df_to_md

        lines = [f"## Regulus review — consolidated across {len(self.assessments)} findings",
                 f"**System under review:** {self.target_system}\n"]
        lines.append("### Findings × risks")
        lines.append(_df_to_md(self.risk_matrix().reset_index()))
        sys_df = self.systemic_provisions()
        lines.append("\n### Systemic anchors (provisions implicated by ≥2 findings)")
        lines.append(_df_to_md(sys_df) if not sys_df.empty else "*(none — findings do not overlap)*")
        lines.append("\n### Consolidated address-first ranking")
        lines.append(_df_to_md(self.consolidated_priority()))
        lines.append("\n---\n_All tables computed by code from one retrieval pass per finding — "
                     "byte-identical across re-runs of the same review._")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<BatchAssessment: {len(self.assessments)} findings for {self.target_system[:50]!r}>"


def assess_batch(
    graph_lookup,
    findings: Dict[str, str],
    target_system: str = "",
    top_k: int = 5,
    with_llm: bool = False,
    config=None,
) -> BatchAssessment:
    """Assess each finding (deterministic core only by default) and consolidate."""
    assessments = {
        name: assess(graph_lookup, text, top_k=top_k, target_system=target_system,
                     config=config, with_llm=with_llm)
        for name, text in findings.items()
    }
    return BatchAssessment(target_system=target_system or "(not specified)", assessments=assessments)


def _core_hash(a: Assessment) -> str:
    """Hash of the deterministic core (LLM narrative excluded)."""
    d = a.to_dict()
    d.pop("llm_interpretation", None)
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def consistency_check(graph_lookup, scenario: str, runs: int = 3, top_k: int = 5) -> pd.DataFrame:
    """Run the same scenario `runs` times; verify the deterministic core is identical.

    This is the multiple-run reproducibility test: every row should show the same
    core hash and `identical to run 1 = True`."""
    hashes = []
    for i in range(runs):
        a = assess(graph_lookup, scenario, top_k=top_k, with_llm=False)
        hashes.append(_core_hash(a))
    return pd.DataFrame([
        {"run": i + 1, "deterministic core hash": h, "identical to run 1": h == hashes[0]}
        for i, h in enumerate(hashes)
    ])
