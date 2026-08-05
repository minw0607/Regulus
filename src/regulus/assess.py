"""Structured, reproducible assessment of a scenario.

This is the layer that answers the user's questions about any scenario — *what
are the risks, which provisions apply (and why), what should we do, and which
provision matters most* — and does so **reproducibly**.

Reproducibility is by design, via a hard split:

- **Deterministic core** (risks, primary provisions, related cross-framework
  provisions, controls, and the graph-derived priority) is computed by code from
  a single retrieval pass over a fixed data store. Same scenario + same store +
  same retriever ⇒ identical core, every run.
- **LLM narrative** (the prose "why" and scenario-specific mitigants) is *labeled*
  as model-generated, runs at ``temperature=0`` with a fixed seed, and only ever
  narrates over the **exact same retrieved provisions** as the deterministic core.

So the facts a governance reviewer relies on are stable and auditable; only the
wording of the explanation can drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .config import RegulusConfig
from .controls import control_for
from .graph_intelligence import GraphReach, PriorityItem, graph_expand, prioritize
from .graph_lookup import GraphLookupResult, RegulusGraphLookup
from .interpret import Interpretation, RegulusInterpreter
from .risk import RISK_TAXONOMY

_RISK_NAME_TO_ID = {rc.name: rc.risk_id for rc in RISK_TAXONOMY}


@dataclass
class PrimaryProvision:
    citation: str
    framework: str
    score: float
    snippet: str
    risks: List[str] = field(default_factory=list)


@dataclass
class RelatedProvision:
    citation: str
    framework: str
    relation: str
    source: str          # citation/provenance of the crosswalk mapping
    related_to: str      # the primary provision this crosswalk hangs off
    rationale: str = ""  # the mapping's own explanation of WHY they are linked


@dataclass
class Assessment:
    """The full, reproducible assessment of one scenario."""

    scenario: str
    target_system: str
    top_k: int
    retriever: str
    generation_model: str
    # deterministic core -----------------------------------------------------
    risks: List[Tuple[str, List[str]]]          # (risk category, provisions that address it)
    primary: List[PrimaryProvision]             # top applicable provisions, ranked
    related: List[RelatedProvision]             # cited cross-framework provisions
    priority: List[PriorityItem] = field(default_factory=list)   # leverage ranking
    graph_reach: List[GraphReach] = field(default_factory=list)  # provisions surfaced via graph
    # labeled LLM narrative --------------------------------------------------
    interpretation: Optional[Interpretation] = None

    # ---- tabular views (deterministic) ------------------------------------
    def top_risks(self, n: int = 3) -> pd.DataFrame:
        """The top-N risks for this scenario, ranked with an explainable score.

        A risk's score is the summed retrieval relevance of the primary provisions
        that address it — so a risk ranks high when *several strong* hits point at
        it, not merely because many weak ones mention a keyword. The `why` column
        names the driving provisions and the control objective. Deterministic:
        same scenario + store ⇒ same ranking, every run.
        """
        rel_by_citation = {p.citation: p.score for p in self.primary}
        rows = []
        for risk, provs in self.risks:
            drivers = sorted(provs, key=lambda c: -rel_by_citation.get(c, 0.0))
            score = sum(rel_by_citation.get(c, 0.0) for c in provs)
            ctrl = control_for(_RISK_NAME_TO_ID.get(risk, ""))
            driver_str = "; ".join(f"{c.split(' — ')[0]} ({rel_by_citation.get(c, 0):.2f})" for c in drivers[:3])
            why = (f"{len(provs)} of the {len(self.primary)} retrieved provisions address it — "
                   f"strongest: {drivers[0].split(' — ')[0]}. Control objective: {ctrl.objective}")
            rows.append({"rank": 0, "risk": risk, "score": round(score, 3),
                         "driving provisions (relevance)": driver_str, "why": why})
        rows.sort(key=lambda r: (-r["score"], r["risk"]))
        for i, r in enumerate(rows[:n], 1):
            r["rank"] = i
        return pd.DataFrame(rows[:n])

    def risk_table(self) -> pd.DataFrame:
        """Risk × relevant standards × suggested control — the at-a-glance summary."""
        rows = []
        for risk, provs in self.risks:
            ctrl = control_for(_RISK_NAME_TO_ID.get(risk, ""))
            rows.append({
                "risk": risk,
                "relevant provisions (standards)": " | ".join(provs) if provs else "—",
                "suggested control / mitigant": ctrl.objective,
            })
        return pd.DataFrame(rows, columns=["risk", "relevant provisions (standards)", "suggested control / mitigant"])

    def priority_table(self) -> pd.DataFrame:
        rows = []
        for i, p in enumerate(self.priority, 1):
            rows.append({
                "rank": i,
                "provision": p.citation,
                "relevance": p.relevance,
                "frameworks linked": len(p.frameworks_linked),
                "findings connected": len(p.connected_findings),
                "leverage": p.leverage,
                "priority score": p.priority,
            })
        return pd.DataFrame(rows)

    def reach_table(self) -> pd.DataFrame:
        rows = [{
            "provision (via graph)": r.citation,
            "framework": r.framework,
            "hops": r.hops,
            "path": " → ".join(r.path),
            "why linked (signal)": (f"{r.relation}: {r.rationale}" if r.rationale else r.relation),
        } for r in self.graph_reach]
        return pd.DataFrame(rows, columns=["provision (via graph)", "framework", "hops", "path", "why linked (signal)"])

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "target_system": self.target_system,
            "retriever": self.retriever,
            "generation_model": self.generation_model,
            "top_k": self.top_k,
            "risks": [{"risk": r, "provisions": p} for r, p in self.risks],
            "primary_provisions": [
                {"citation": p.citation, "framework": p.framework, "relevance": p.score, "risks": p.risks}
                for p in self.primary
            ],
            "related_provisions": [
                {"citation": r.citation, "framework": r.framework, "relation": r.relation,
                 "source": r.source, "related_to": r.related_to, "rationale": r.rationale}
                for r in self.related
            ],
            "priority": [
                {"citation": p.citation, "relevance": p.relevance, "frameworks_linked": p.frameworks_linked,
                 "connected_findings": p.connected_findings, "leverage": p.leverage,
                 "centrality": p.centrality, "priority_score": p.priority}
                for p in self.priority
            ],
            "graph_reach": [
                {"citation": r.citation, "framework": r.framework, "hops": r.hops,
                 "path": r.path, "relation": r.relation, "source": r.source,
                 "rationale": r.rationale, "signals": r.signals}
                for r in self.graph_reach
            ],
            "controls": [
                {"risk": rc.name, "objective": control_for(rc.risk_id).objective,
                 "activities": list(control_for(rc.risk_id).activities)}
                for rc in RISK_TAXONOMY if rc.name in {r for r, _ in self.risks}
            ],
            "llm_interpretation": self.interpretation.answer_markdown if self.interpretation else None,
        }

    @property
    def linchpin(self) -> Optional[PriorityItem]:
        return self.priority[0] if self.priority else None

    def __repr__(self) -> str:  # compact — avoids a wall of text when echoed in a notebook
        lp = self.linchpin.citation if self.linchpin else "—"
        return (f"<Assessment: {len(self.primary)} provisions, {len(self.risks)} risks, "
                f"{len(self.graph_reach)} graph reaches; linchpin: {lp[:60]}>")

    def evidence_paths(self, limit: int = 3) -> List[str]:
        """The most instructive reach chains, rendered node —[signal]→ node.

        Multi-hop chains first (they show relationships similarity can't see),
        then cross-framework 1-hop links. Every hop shows its own signal."""
        ranked = sorted(self.graph_reach, key=lambda r: (-r.hops, r.framework, r.citation))
        out = []
        for r in ranked[:limit]:
            parts = [r.path[0]]
            for node, sig in zip(r.path[1:], r.signals):
                parts.append(f" —[{sig[:110]}]→ {node}")
            out.append("".join(parts))
        return out

    # ---- rendering --------------------------------------------------------
    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"## Regulus assessment")
        lines.append(f"**System under review:** {self.target_system}")
        lines.append(f"**Scenario:** {self.scenario}\n")

        # 1) Risk × standards × control table (led by the ranked top risks)
        lines.append("### 1. Risks, standards & controls")
        top = self.top_risks(3)
        if not top.empty:
            lines.append("**Top risks (ranked by summed relevance of the provisions addressing them):**\n")
            lines.append(_df_to_md(top[["rank", "risk", "score", "driving provisions (relevance)"]]))
            lines.append("\n**All risks identified:**\n")
        lines.append(_df_to_md(self.risk_table()))

        # 2) Priority — the GKN insight
        lines.append("\n### 2. Priority — what to address first (graph leverage)")
        if self.linchpin is not None:
            lp = self.linchpin
            lines.append(
                f"**Linchpin: {lp.citation}.** Highest leverage — relevant *and* the most connected "
                f"provision in this scenario: it links {len(lp.frameworks_linked)} framework(s) "
                f"({', '.join(lp.frameworks_linked)}) and shares risks with {len(lp.connected_findings)} "
                f"other finding(s). Addressing it advances the most of the rest.\n"
            )
            lines.append(_df_to_md(self.priority_table()))
        else:
            lines.append("*(no provisions retrieved)*")

        # 3) Cross-framework reach via the graph (not similarity)
        lines.append("\n### 3. Cross-framework reach (via the knowledge graph)")
        if self.graph_reach:
            lines.append(
                "Related provisions the graph surfaces by following cited crosswalks — the *same "
                "concern in other frameworks*, which similarity retrieval alone did not return:\n"
            )
            lines.append(_df_to_md(self.reach_table()))
            paths = self.evidence_paths(limit=3)
            if paths:
                lines.append("\n**Evidence paths** (each hop shows the signal that justifies it):")
                for p in paths:
                    lines.append(f"> {p}")
        else:
            lines.append("*(no additional provisions reachable via crosswalks from the retrieved set)*")

        # 4) LLM narrative (why + scenario-specific mitigants), clearly labeled
        lines.append("\n### 4. Interpretation & recommended mitigants")
        if self.interpretation is not None and self.interpretation.answer_markdown:
            lines.append(
                f"_Generated by {self.generation_model} at temperature 0 (labeled, best-effort "
                f"reproducible) over the exact provisions above._\n"
            )
            lines.append(self.interpretation.answer_markdown)
        elif self.interpretation is not None:
            lines.append(f"_LLM narrative not generated: {self.interpretation.note}._")
            lines.append(
                "\nThe deterministic core above (risks, provisions, controls, priority) is complete "
                "and reproducible without the LLM."
            )
        else:
            lines.append("_(LLM narrative disabled.)_")

        # reproducibility footer
        lines.append(
            f"\n---\n_Reproducibility: sections 1–3 are computed by code from a single retrieval pass "
            f"(retriever: **{self.retriever}**, top_k={self.top_k}) over a fixed data store — identical "
            f"on every run for the same scenario. Only the wording of section 4 may vary._"
        )
        return "\n".join(lines)


def _df_to_md(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavored Markdown table (no tabulate dep)."""
    if df.empty:
        return "*(none)*"
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = [str(v).replace("|", "\\|").replace("\n", " ") for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _aggregate_risks(results: List[GraphLookupResult]) -> List[Tuple[str, List[str]]]:
    """Map each risk category to the retrieved provisions that address it.

    Ordered by how many provisions address the risk (descending), then name — a
    deterministic ordering independent of dict insertion.
    """
    by_risk: Dict[str, List[str]] = {}
    for r in results:
        for risk in r.risks:
            by_risk.setdefault(risk, [])
            if r.provision.citation() not in by_risk[risk]:
                by_risk[risk].append(r.provision.citation())
    return sorted(by_risk.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def assess(
    graph_lookup: RegulusGraphLookup,
    scenario: str,
    top_k: int = 5,
    target_system: str = "",
    interpreter: Optional[RegulusInterpreter] = None,
    config: Optional[RegulusConfig] = None,
    with_llm: bool = True,
    max_hops: int = 2,
) -> Assessment:
    """Produce a reproducible :class:`Assessment` for ``scenario``.

    One retrieval pass feeds the deterministic core (risks, provisions, controls,
    graph priority and reach) and, optionally, the LLM narrative — guaranteeing
    they all describe the same provisions.
    """
    cfg = config or graph_lookup.config
    results = graph_lookup.search(scenario, top_k=top_k)

    primary = [
        PrimaryProvision(
            citation=r.provision.citation(),
            framework=r.provision.framework_name,
            score=round(r.score, 3),
            snippet=r.snippet.strip()[:300],
            risks=r.risks,
        )
        for r in results
    ]
    related: List[RelatedProvision] = []
    seen = set()
    for r in results:
        for cx in r.crosswalks:
            key = (cx.provision.citation(), r.provision.citation())
            if key in seen:
                continue
            seen.add(key)
            related.append(
                RelatedProvision(
                    citation=cx.provision.citation(),
                    framework=cx.provision.framework_name,
                    relation=cx.relation,
                    source=cx.source,
                    related_to=r.provision.citation(),
                    rationale=cx.rationale,
                )
            )

    priority = prioritize(graph_lookup, results, max_hops=max_hops)
    reach = graph_expand(graph_lookup, results, max_hops=max_hops)

    interpretation: Optional[Interpretation] = None
    if with_llm:
        interp = interpreter or RegulusInterpreter(graph_lookup, cfg, target_system=target_system)
        # Reuse the SAME retrieved results so the narrative can't drift from the core.
        interpretation = interp.interpret_results(scenario, results)

    return Assessment(
        scenario=scenario,
        target_system=target_system or "(not specified)",
        top_k=top_k,
        retriever=graph_lookup.lookup.retriever,
        generation_model=cfg.openai_generation_model,
        risks=_aggregate_risks(results),
        primary=primary,
        related=related,
        priority=priority,
        graph_reach=reach,
        interpretation=interpretation,
    )
