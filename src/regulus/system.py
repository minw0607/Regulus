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

from .config import RegulusConfig
from .graph import graph_summary
from .graph_lookup import RegulusGraphLookup
from .ingest.base import Provision
from .interpret import Interpretation, RegulusInterpreter

# All frameworks registered today (real text, or reference snapshot for ISO).
ALL_STANDARDS: tuple[str, ...] = ("eu_ai_act", "nist_ai_rmf", "nist_ai_600_1", "oecd_ai", "iso_42001")


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
            ("retriever", self.config.retriever),
            ("LLM interpretation", f"ready ({self.config.openai_generation_model})" if llm_reason is None else f"not configured — {llm_reason}"),
            ("target system", self.target_system or "(not specified)"),
        ]
        return pd.DataFrame(rows, columns=["property", "value"])

    # ---- core operations --------------------------------------------------
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
        try:
            from IPython.display import Markdown, display

            display(Markdown(text))
        except Exception:
            print(text)
        return result

    def visualize(self, issue: str, top_k: int = 3):
        from . import demo

        return demo.draw_issue_graph(self.graph_lookup, issue, top_k=top_k)

    def framework_map(self):
        from . import demo

        return demo.draw_framework_map(self.graph_lookup)
