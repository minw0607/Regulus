"""LLM interpretation layer — grounded, cited synthesis over retrieved provisions.

This is Regulus's answer to *"how is this better than traditional RAG?"* The LLM
does not receive flat retrieved text; it receives **structured context** — the
applicable provisions *plus their typed relationships* (cited cross-framework
crosswalks and the risks they address). Its job is to interpret and synthesize,
never to author regulation:

- use ONLY the provisions in the context — never invent a provision or requirement;
- present crosswalks as *curated* related guidance (with their source note);
- cite every claim with the provision id.

The interpreter reuses the same Azure/OpenAI configuration as retrieval. Without
an API key it returns the structured context it *would* send (``dry_run``), so the
pipeline is inspectable even offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .config import RegulusConfig
from .graph_lookup import RegulusGraphLookup

_SYSTEM_PROMPT = """You are Regulus, an AI-governance and model-risk assistant. Given a user's issue \
or observation and a CONTEXT of retrieved regulatory provisions (with their cross-framework \
relationships), you map the issue to the provisions that govern it and explain the connections.

STRICT RULES:
1. Use ONLY the provisions in the CONTEXT. Never cite a provision, requirement, or mapping that is \
not present in the context. If the context is insufficient, say so plainly.
2. Cross-framework crosswalks in the context are CURATED mappings — present them as "related \
guidance", and carry their source note (e.g. authoritative vs "curated seed — verify").
3. Cite every substantive claim inline with the provision id (e.g. "EU AI Act Article 5", \
"NIST AI RMF MEASURE 2.11").
4. You interpret and synthesize; you do NOT author regulation. Do not state obligations that are \
not grounded in a cited provision.
5. Be concise and practical for a governance / model-risk audience.
"""

_USER_TEMPLATE = """AI SYSTEM UNDER REVIEW:
{target_system}

ISSUE / OBSERVATION:
{issue}

CONTEXT (retrieved provisions and their cited relationships):
{context}

Produce a structured response in Markdown:
1. **Why these provisions apply** — for each provision in the context, one sentence on *why it applies to this specific system/scenario* (cite it).
2. **Root cause & related provisions** — the root governance gap, and how the cross-framework *related* provisions (the crosswalks) reinforce or extend the primary ones (note their source).
3. **Recommended mitigants** — concrete, actionable steps to address the risks and root cause. **Each mitigant must be grounded in and cite a specific provision** (the provision's own obligation is the basis) — do not invent obligations.

Cite provisions inline. Keep it practical for a model-risk audience.
"""


_GRAPH_SYSTEM_PROMPT = """You are Regulus, an AI-governance assistant. You are given DETERMINISTIC FACTS \
about one scenario's neighborhood in a regulatory knowledge graph (its directly-retrieved provisions, \
the related provisions reached across frameworks via cited crosswalks, the risks involved, and the \
highest-leverage 'linchpin' provision). Write a short, plain reading of that neighborhood.

STRICT RULES:
1. Use ONLY the provisions and facts given. Never introduce a provision, framework, risk, or mapping \
that is not in the facts.
2. Do not change any number, citation, or the linchpin — narrate them, don't revise them.
3. Follow the requested structure exactly. Be concise (governance / model-risk audience).
"""

_GRAPH_USER_TEMPLATE = """SCENARIO:
{scenario}

DETERMINISTIC FACTS (the same data the diagram is drawn from):
{facts}

Write the reading in Markdown with EXACTLY these four bullets, filling the prose but keeping every \
citation and number from the facts:

- **What the scenario implicates:** <the direct-hit provision(s), and in one clause why>.
- **How the frameworks connect:** <the cross-framework provisions reached via crosswalks, and what shared concern links them; if none were reached, say the concern is currently mapped in one framework only>.
- **Risks in play:** <the risk categories, noting which links the most findings>.
- **Where to start:** <the linchpin provision and why addressing it has the most leverage>.
"""


@dataclass
class Interpretation:
    issue: str
    context: str
    citations: List[str]
    answer_markdown: Optional[str] = None   # None in dry-run / no-API mode
    model: str = ""
    note: str = ""

    def display(self) -> str:
        if self.answer_markdown:
            return self.answer_markdown
        return f"*(dry run — no LLM called: {self.note})*\n\n**Structured context that would be sent:**\n\n{self.context}"

    def __repr__(self) -> str:  # compact — avoids a wall of text when echoed in a notebook
        state = f"answered by {self.model}" if self.answer_markdown else f"dry run ({self.note})"
        return f"<Interpretation: {len(self.citations)} citations; {state}>"


class RegulusInterpreter:
    def __init__(
        self,
        graph_lookup: RegulusGraphLookup,
        config: RegulusConfig | None = None,
        target_system: str = "",
    ) -> None:
        self.graph_lookup = graph_lookup
        self.config = config or RegulusConfig()
        self.target_system = target_system or "(not specified)"

    def build_context_from_results(self, results) -> tuple[str, List[str]]:
        """Assemble the structured, cited context from already-retrieved results."""
        blocks: List[str] = []
        citations: List[str] = []
        for i, r in enumerate(results, 1):
            citations.append(r.provision.citation())
            lines = [f"[{i}] {r.provision.citation()}  (source: {r.provision.source_url})"]
            lines.append(f"    text: {r.snippet.strip()[:400]}")
            if r.risks:
                lines.append(f"    risks addressed: {', '.join(r.risks)}")
            for cx in r.crosswalks:
                lines.append(f"    ↔ related: {cx.provision.citation()}  [{cx.relation}; source: {cx.source}]")
                if cx.provision.citation() not in citations:
                    citations.append(cx.provision.citation())
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) if blocks else "(no provisions retrieved)", citations

    def build_context(self, issue: str, top_k: int = 5) -> tuple[str, List[str]]:
        return self.build_context_from_results(self.graph_lookup.search(issue, top_k=top_k))

    def interpret(self, issue: str, top_k: int = 5, temperature: float = 0.0, max_tokens: int = 1500) -> Interpretation:
        return self.interpret_results(issue, self.graph_lookup.search(issue, top_k=top_k), temperature, max_tokens)

    def interpret_results(self, issue: str, results, temperature: float = 0.0, max_tokens: int = 1500) -> Interpretation:
        """Interpret a *precomputed* result set (so the narrative uses the exact same
        retrieved provisions as the deterministic assessment)."""
        context, citations = self.build_context_from_results(results)

        reason = self._llm_unavailable_reason()
        if reason is not None:
            return Interpretation(issue=issue, context=context, citations=citations, note=reason)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(
                target_system=self.target_system, issue=issue, context=context)},
        ]
        response = self._chat_create(self._build_client(), messages, temperature, max_tokens)
        answer = response.choices[0].message.content
        return Interpretation(
            issue=issue, context=context, citations=citations,
            answer_markdown=answer, model=self.config.openai_generation_model,
        )

    def describe_neighborhood(self, summary, temperature: float = 0.0, max_tokens: int = 500):
        """LLM 'reading' of a neighborhood, constrained to the deterministic facts.

        ``summary`` is a ``graph_intelligence.NeighborhoodSummary``. Returns the
        narrative Markdown, or ``None`` (with the reason) when no LLM is available —
        callers should fall back to ``summary.to_markdown()`` (fully reproducible)."""
        reason = self._llm_unavailable_reason()
        if reason is not None:
            return None, reason
        facts = summary.to_markdown()
        messages = [
            {"role": "system", "content": _GRAPH_SYSTEM_PROMPT},
            {"role": "user", "content": _GRAPH_USER_TEMPLATE.format(scenario=summary.scenario, facts=facts)},
        ]
        response = self._chat_create(self._build_client(), messages, temperature, max_tokens)
        return response.choices[0].message.content, None

    def _chat_create(self, client, messages, temperature: float, max_tokens: int, seed: int = 7):
        """Call chat.completions.create, adapting to model-specific parameter rules.

        Models disagree on `max_tokens` vs `max_completion_tokens`, on whether a
        custom `temperature` is allowed (newer reasoning models require the default),
        and on `seed`. We request temperature 0 + a fixed seed first (for best-effort
        reproducibility) and fall back through every combination until one is accepted."""
        from itertools import product

        model = self.config.openai_generation_model
        base = {"model": model, "messages": messages}
        try:
            from openai import BadRequestError, UnprocessableEntityError
            retryable: tuple = (BadRequestError, UnprocessableEntityError, TypeError)
        except Exception:  # pragma: no cover
            retryable = (Exception,)

        token_opts = [{"max_completion_tokens": max_tokens}, {"max_tokens": max_tokens}, {}]
        temp_opts = [{"temperature": temperature}, {}]
        seed_opts = [{"seed": seed}, {}]
        last = None
        for tok, tmp, sd in product(token_opts, temp_opts, seed_opts):
            try:
                return client.chat.completions.create(**base, **tok, **tmp, **sd)
            except retryable as exc:  # noqa: PERF203
                last = exc
                continue
        raise last

    # ---- LLM client (reuses the Azure/OpenAI config used for embeddings) -----
    def _llm_unavailable_reason(self) -> Optional[str]:
        try:
            import openai  # noqa: F401
        except ImportError:
            return "the 'openai' package is not installed (pip install openai)"
        if not self.config.openai_api_key:
            return "OPENAI_API_KEY is not set"
        return None

    def _build_client(self):
        from openai import AzureOpenAI, OpenAI

        headers = {}
        if self.config.openai_apim_header_name and self.config.openai_apim_subscription_key:
            headers[self.config.openai_apim_header_name] = self.config.openai_apim_subscription_key
        if self.config.openai_api_version:
            return AzureOpenAI(
                api_key=self.config.openai_api_key,
                azure_endpoint=self.config.openai_base_url,
                api_version=self.config.openai_api_version,
                default_headers=headers or None,
            )
        return OpenAI(
            api_key=self.config.openai_api_key,
            base_url=self.config.openai_base_url or None,
            default_headers=headers or None,
        )
