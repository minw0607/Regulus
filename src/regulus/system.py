"""RegulusSystem — a single facade over the whole pipeline.

Configure once, then use one call per step. This keeps notebooks/apps code-light:

    reg = RegulusSystem.launch(
        standards=["eu_ai_act", "nist_ai_rmf", ...],
        retriever="embedding",
        target_system="A credit-scoring model used to approve/deny consumer loans.",
    )
    reg.info()             # what's loaded, retriever, whether the LLM is configured
    reg.lookup(scenario)   # retrieval only (applicable provisions)
    reg.analyze(scenario)  # retrieval + graph + LLM interpretation (grounded, cited)
    reg.visualize(scenario)

It is, in one line, **RAG + a knowledge network**: retrieval over real regulatory
text, enriched by a cited cross-framework graph, optionally interpreted by an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import pandas as pd

from .assess import Assessment, _df_to_md, assess
from .config import RegulusConfig
from .graph import graph_summary
from .graph_lookup import RegulusGraphLookup
from .ingest.base import Provision
from .interpret import Interpretation, RegulusInterpreter

# All frameworks registered today (real text, or reference snapshot for ISO).
ALL_STANDARDS: tuple[str, ...] = ("eu_ai_act", "nist_ai_rmf", "nist_ai_600_1", "oecd_ai", "iso_42001")


def _render_markdown(text: str) -> str:
    """Render Markdown in a notebook if possible, else print. Returns the text."""
    try:
        from IPython.display import Markdown, display

        display(Markdown(text))
    except Exception:
        print(text)
    return text


@dataclass
class RegulusSystem:
    config: RegulusConfig
    provisions: List[Provision]
    graph_lookup: RegulusGraphLookup
    interpreter: RegulusInterpreter
    standards: List[str] = field(default_factory=list)
    target_system: str = ""

    @classmethod
    def launch(
        cls,
        standards: Optional[Sequence[str]] = None,
        retriever: Optional[str] = None,
        target_system: str = "",
        top_k: Optional[int] = None,
        config: Optional[RegulusConfig] = None,
    ) -> "RegulusSystem":
        cfg = config or RegulusConfig()
        if retriever:
            cfg.retriever = retriever
        if top_k:
            cfg.top_k = top_k
        standards = list(standards) if standards else list(ALL_STANDARDS)

        from .standards_loader import StandardsLoader

        provisions = StandardsLoader(cfg).load(framework_ids=standards)
        graph_lookup = RegulusGraphLookup(provisions, cfg)
        interpreter = RegulusInterpreter(graph_lookup, cfg, target_system=target_system)
        return cls(cfg, provisions, graph_lookup, interpreter, standards, target_system)

    # ---- inspection -------------------------------------------------------
    def info(self) -> pd.DataFrame:
        summary = graph_summary(self.graph_lookup.graph)
        from collections import Counter

        by_fw = Counter(p.framework_name for p in self.provisions)
        llm_reason = self.interpreter._llm_unavailable_reason()
        rows = [
            ("frameworks loaded", ", ".join(sorted(by_fw))),
            ("provisions", str(summary.get("node:Provision", 0))),
            ("crosswalk edges", str(summary.get("edge:CROSSWALK", 0))),
            ("risk categories", str(summary.get("node:RiskCategory", 0))),
            ("retriever", f"{self.graph_lookup.lookup.retriever} (configured: {self.config.retriever})"),
            ("LLM interpretation", f"ready ({self.config.openai_generation_model})" if llm_reason is None else f"not configured — {llm_reason}"),
            ("target system", self.target_system or "(not specified)"),
        ]
        return pd.DataFrame(rows, columns=["property", "value"])

    def overview(self):
        """A one-glance 'app card' for the launched system: what it is, the models it
        uses, the data it covers, the knowledge-network shape, and its I/O contract.
        Renders as Markdown in a notebook; returns the Markdown string."""
        import os
        from collections import Counter

        summary = graph_summary(self.graph_lookup.graph)
        by_fw = Counter(p.framework_name for p in self.provisions)
        fw_lines = "\n".join(f"  - {name} — {n} provisions" for name, n in sorted(by_fw.items()))
        retriever = self.graph_lookup.lookup.retriever
        embed_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        embed_desc = f"`{embed_model}` (dense) " if retriever == "embedding" else "TF-IDF (lexical, no API) "
        llm_reason = self.interpreter._llm_unavailable_reason()
        llm_desc = (
            f"`{self.config.openai_generation_model}` at temperature 0"
            if llm_reason is None else f"not configured — {llm_reason} (deterministic core still works)"
        )
        md = f"""## Regulus — AI-governance standards lookup

**What it is.** Domain-specialized GraphRAG for AI governance. You describe an AI
system and a scenario; Regulus retrieves the applicable provisions across multiple
frameworks, links them through a **cited cross-framework knowledge network**, and
(optionally) has an LLM interpret them into a grounded, cited assessment.

**Models**
- *Retrieval / embeddings:* {embed_desc}over provision-scoped units.
- *Generation (interpretation):* {llm_desc}.

**Regulatory data store ({summary.get('node:Provision', 0)} provisions across {len(by_fw)} frameworks)**
{fw_lines}

**Knowledge network (KN) structure**
- Nodes: `Framework` → `Provision` → `RiskCategory`.
- Edges: `CONTAINS` (framework→provision), `ADDRESSES` (provision→risk),
  `CROSSWALK` (provision↔provision across frameworks — **curated & cited, never
  LLM-invented**).
- Size: {summary.get('node:Provision', 0)} provisions · {summary.get('edge:CROSSWALK', 0)} crosswalk edges ·
  {summary.get('node:RiskCategory', 0)} risk categories.

**Input** — a plain-language scenario/observation (e.g. *"our credit model was
deployed without testing for demographic bias"*), plus an optional description of
the system under review.

**Output** — a structured assessment: (1) the **risks**, (2) the **applicable
provisions** (primary + cited related provisions in other frameworks), and
(3) an **interpretation with recommended mitigants**, each grounded in a cited
provision.

**Reproducibility** — the risks and provisions are computed by code from a single
retrieval pass over a fixed data store, so the same scenario yields the **same
core** every run. Only the LLM's wording (section 3) may vary; it is labeled and
runs at temperature 0.
"""
        return _render_markdown(md)

    # ---- core operations --------------------------------------------------
    def assess(self, scenario: str, top_k: Optional[int] = None, with_llm: bool = True,
               render: bool = True, export: bool = False, export_dir: str = "artifacts/assessments"):
        """Full reproducible assessment: risks × standards × controls, graph-leverage
        priority, cross-framework reach (deterministic core) + labeled LLM narrative.

        Returns the :class:`Assessment`; renders its Markdown by default. Set
        ``export=True`` to also save Markdown/JSON/CSV into ``export_dir`` (the
        saved folder path is printed and available on ``assessment`` via export)."""
        result = assess(
            self.graph_lookup,
            scenario,
            top_k=top_k or self.config.top_k,
            target_system=self.target_system,
            interpreter=self.interpreter,
            config=self.config,
            with_llm=with_llm,
        )
        if render:
            _render_markdown(result.to_markdown())
        if export:
            folder = self.export(result, out_dir=export_dir)
            print(f"[saved] {folder}")
        return result

    def export(self, assessment, out_dir: str = "artifacts/assessments"):
        """Save an assessment (Markdown + JSON + CSV tables) to a local folder."""
        from .export import export_assessment

        return export_assessment(assessment, out_dir=out_dir)

    def priority(self, scenario: str, top_k: Optional[int] = None) -> pd.DataFrame:
        """Graph-leverage ranking of the retrieved provisions (linchpin first)."""
        from .graph_intelligence import prioritize

        results = self.graph_lookup.search(scenario, top_k=top_k or self.config.top_k)
        items = prioritize(self.graph_lookup, results)
        rows = [{
            "rank": i,
            "provision": p.citation,
            "relevance": p.relevance,
            "frameworks linked": ", ".join(p.frameworks_linked),
            "findings connected": len(p.connected_findings),
            "leverage": p.leverage,
            "priority score": p.priority,
        } for i, p in enumerate(items, 1)]
        return pd.DataFrame(rows)

    def compare_rag(self, scenario: str, top_k: Optional[int] = None, render: bool = True) -> pd.DataFrame:
        """Flat RAG vs GraphRAG on this scenario — what the knowledge network adds."""
        from .graph_intelligence import rag_vs_graph

        c = rag_vs_graph(self.graph_lookup, scenario, top_k=top_k or self.config.top_k)
        rows = [
            ("provisions surfaced", c.flat_provisions, c.flat_provisions + c.graph_extra_provisions),
            ("frameworks covered", len(c.flat_frameworks), len(c.graph_frameworks)),
            ("cross-framework links used", 0, c.crosswalk_links),
            ("risks identified", 0, len(c.risks_identified)),
            ("prioritized 'address-first'", "—", c.linchpin or "—"),
        ]
        df = pd.DataFrame(rows, columns=["dimension", "flat RAG (similarity only)", "Regulus GraphRAG"])
        if render:
            note = ("" if c.linchpin_is_top1 else
                    f"\n\n_Note: leverage re-ranked the priority away from the similarity top-1 — "
                    f"the graph considers **{c.linchpin}** the highest-impact provision to address first._")
            _render_markdown(f"### Flat RAG vs Regulus GraphRAG — *{scenario[:80]}*\n\n"
                             + _df_to_md(df) + note)
        return df

    def coverage(self, scenarios, top_k: Optional[int] = None) -> pd.DataFrame:
        """Run several scenarios and report which frameworks, risks and provisions
        get exercised — a quick view of how well the corpus covers a test set."""
        top_k = top_k or self.config.top_k
        items = scenarios.items() if isinstance(scenarios, dict) else [(s, s) for s in scenarios]
        rows = []
        for name, text in items:
            results = self.graph_lookup.search(text, top_k=top_k)
            frameworks = sorted({r.provision.framework_name for r in results})
            risks = sorted({risk for r in results for risk in r.risks})
            rows.append({
                "scenario": name if isinstance(scenarios, dict) else name[:50],
                "top provision": results[0].provision.citation() if results else "—",
                "frameworks hit": len(frameworks),
                "risks identified": len(risks),
                "risk categories": ", ".join(risks) or "—",
            })
        return pd.DataFrame(rows)

    def lookup(self, issue: str, top_k: Optional[int] = None) -> pd.DataFrame:
        top_k = top_k or self.config.top_k
        rows = []
        for r in self.graph_lookup.search(issue, top_k=top_k):
            refs = " | ".join(cx.provision.citation() for cx in r.crosswalks) or "—"
            rows.append(
                {
                    "provision": r.provision.citation(),
                    "score": round(r.score, 3),
                    "risks addressed": ", ".join(r.risks) or "—",
                    "cross-framework references (cited)": refs,
                }
            )
        return pd.DataFrame(rows)

    def analyze(self, issue: str, top_k: Optional[int] = None) -> Interpretation:
        return self.interpreter.interpret(issue, top_k=top_k or self.config.top_k)

    def answer(self, issue: str, top_k: Optional[int] = None) -> Interpretation:
        """Interpret an issue and render the (grounded, cited) result as Markdown."""
        result = self.analyze(issue, top_k=top_k)
        text = f"### Regulus — interpretation\n**System under review:** {self.target_system}\n\n**Issue:** {issue}\n\n{result.display()}"
        _render_markdown(text)
        return result

    def describe_neighborhood(self, scenario: str, top_k: int = 3, with_llm: bool = True, render: bool = False) -> str:
        """A reading of the scenario's neighborhood, built on deterministic facts.

        Facts (direct hits, cross-framework reach, risks, linchpin) are computed by
        code from the same graph the diagram is drawn from, filling a fixed template
        — fully reproducible. With ``with_llm`` and an API key, the LLM narrates those
        exact facts (temperature 0, labeled); otherwise the template itself is used."""
        from .graph_intelligence import summarize_neighborhood

        summary = summarize_neighborhood(self.graph_lookup, scenario, top_k=top_k)
        facts_md = summary.to_markdown()
        text = facts_md
        if with_llm:
            narrative, reason = self.interpreter.describe_neighborhood(summary)
            if narrative:
                text = (
                    f"_Reading generated by {self.config.openai_generation_model} at temperature 0 "
                    f"(labeled, grounded in the deterministic facts below)._\n\n"
                    f"{narrative}\n\n"
                    f"**Facts (deterministic, reproducible):**\n\n{facts_md}"
                )
        if render:
            _render_markdown(text)
        return text

    def visualize(self, issue: str, top_k: int = 3, describe: bool = True, with_llm: bool = True):
        """Draw the regulatory neighborhood and, by default, render a description of it
        beneath the figure (deterministic template, optionally narrated by the LLM)."""
        from . import demo

        fig = demo.draw_issue_graph(self.graph_lookup, issue, top_k=top_k)
        if describe:
            self.describe_neighborhood(issue, top_k=top_k, with_llm=with_llm, render=True)
        return fig

    def framework_map(self):
        from . import demo

        return demo.draw_framework_map(self.graph_lookup)

    def evaluate_retrieval(self, eval_set=None, top_k: int = 5) -> pd.DataFrame:
        """Measure retrieval quality against a labelled issue -> expected-provisions set."""
        from .eval import retrieval_report

        return retrieval_report(self.graph_lookup, eval_set=eval_set, top_k=top_k)
