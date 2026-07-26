"""Provision-aware indexing — turn provisions into good retrieval units.

Regulatory text is not arbitrary prose: a provision is a self-contained, citable
unit. So the retrieval unit is the **provision** (not a fixed-size character
window). Long provisions are split on *sentence* boundaries into a few units, and
every unit carries a short header (framework · provision id · title) so the
framework and subject contribute to the semantic match. This fixes the two big
weaknesses of generic chunking: units that start mid-sentence, and "snippets" that
were just the citation header.
"""
from __future__ import annotations

import re
from typing import List

from geometric_knowledge_network.ingest import Chunk

from .ingest.base import Provision

_SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _pack(sentences: List[str], max_chars: int) -> List[str]:
    """Greedily pack sentences into units no larger than ``max_chars``."""
    units: List[str] = []
    current: List[str] = []
    length = 0
    for sentence in sentences:
        if current and length + len(sentence) > max_chars:
            units.append(" ".join(current))
            current, length = [], 0
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        units.append(" ".join(current))
    return units or [" ".join(sentences)]


def _header(provision: Provision) -> str:
    header = f"{provision.framework_name} — {provision.provision_id}"
    return f"{header}: {provision.title}" if provision.title else header


def build_units(provisions: List[Provision], max_chars: int = 900) -> List[Chunk]:
    """Build provision-scoped retrieval units (as GKN Chunks).

    ``doc_id`` is the provision's unique id, so retrieval results dedupe back to
    provisions. ``text`` is a header + normative text, so both the embedding and
    the snippet shown to the LLM carry the actual provision content.
    """
    chunks: List[Chunk] = []
    for provision in provisions:
        header = _header(provision)
        body = (provision.text or "").strip()
        parts = [body] if len(body) <= max_chars else _pack(_sentences(body), max_chars)
        for i, part in enumerate(parts):
            text = f"{header}\n{part}".strip()
            chunks.append(
                Chunk(
                    chunk_id=f"{provision.unique_id()}#{i}",
                    doc_id=provision.unique_id(),
                    text=text,
                    start_idx=0,
                    end_idx=len(text),
                )
            )
    return chunks
