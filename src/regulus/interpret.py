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
1. **Assessment** — what the issue implicates, in 2-3 sentences.
2. **Applicable provisions** — for each, the citation, *why it applies to this issue*, and the risk(s) it addresses.
3. **Cross-framework view** — how the concern maps across frameworks, using the crosswalks (note their source).
4. **Suggested next steps** — concrete, grounded actions.

Cite provisions inline. End with a **Sources** list of the provisions you referenced.
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

    def build_context(self, issue: str, top_k: int = 5) -> tuple[str, List[str]]:
        """Assemble the structured, cited context from the graph lookup."""
        results = self.graph_lookup.search(issue, top_k=top_k)
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

    def interpret(self, issue: str, top_k: int = 5, temperature: float = 0.2, max_tokens: int = 1500) -> Interpretation:
        context, citations = self.build_context(issue, top_k=top_k)

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

    def _chat_create(self, client, messages, temperature: float, max_tokens: int):
        """Call chat.completions.create, adapting to model-specific parameter rules.

        Models disagree on `max_tokens` vs `max_completion_tokens` and on whether a
        custom `temperature` is allowed (newer reasoning models require the default).
        Try progressively simpler parameter sets until one is accepted."""
        model = self.config.openai_generation_model
        base = {"model": model, "messages": messages}
        attempts = [
            {**base, "temperature": temperature, "max_completion_tokens": max_tokens},
            {**base, "max_completion_tokens": max_tokens},               # drop temperature
            {**base, "temperature": temperature, "max_tokens": max_tokens},
            {**base, "max_tokens": max_tokens},                          # legacy token param
            {**base},                                                    # bare minimum
        ]
        try:
            from openai import BadRequestError, UnprocessableEntityError
            retryable: tuple = (BadRequestError, UnprocessableEntityError, TypeError)
        except Exception:  # pragma: no cover
            retryable = (Exception,)

        last = None
        for kwargs in attempts:
            try:
                return client.chat.completions.create(**kwargs)
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
