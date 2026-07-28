"""Issue -> applicable provisions lookup, built on the GKN retrieval substrate.

This is the Phase-1 baseline: semantic retrieval over the provision corpus. It
converts each Provision into a GKN document, chunks + indexes it, and maps
retrieved chunks back to their provisions (with provenance). Later phases add the
regulatory knowledge graph and multi-hop crosswalk expansion on top of this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import RegulusConfig
from .indexing import build_units
from .ingest.base import Provision


@dataclass
class LookupResult:
    provision: Provision
    score: float
    snippet: str

    def as_citation(self) -> str:
        return f"{self.provision.citation()}  [{self.provision.source_url}]"


class RegulusLookup:
    def __init__(self, provisions: List[Provision], config: RegulusConfig | None = None) -> None:
        self.config = config or RegulusConfig()
        self.provisions = provisions

        # Exclude non-substantive/procedural provisions from retrieval (definitions,
        # amendments, entry into force, ...) — they impose no obligation and are
        # noise as hits. They remain in the corpus/graph; they just aren't indexed.
        indexable = provisions
        if self.config.filter_non_substantive:
            from .stoplist import filter_substantive

            indexable, removed = filter_substantive(provisions)
            if removed:
                print(f"[INFO] Retrieval index: skipping {len(removed)} non-substantive provision(s) "
                      f"(definitions/amendments/entry-into-force). Set REGULUS_FILTER_NON_SUBSTANTIVE=0 to keep.")
        self._by_id = {p.unique_id(): p for p in indexable}

        # Provision-aware retrieval units (see indexing.build_units).
        self.chunks = build_units(indexable, max_chars=self.config.chunk_size)
        self.retriever = self._resolve_retriever()
        self.vector_store = self._build_vector_store()
        self.vector_store.build(self.chunks)

    def _resolve_retriever(self) -> str:
        """Resolve 'auto' -> 'embedding' if a cloud key is available, else 'tfidf'."""
        choice = (self.config.retriever or "auto").lower()
        if choice == "auto":
            return "embedding" if self.config.openai_api_key else "tfidf"
        return choice

    def _build_vector_store(self):
        if self.retriever == "embedding":
            # Reuse GKN's embedding store (Azure/OpenAI or local, per GKN env vars),
            # with its faiss/openai/local fallbacks.
            from geometric_knowledge_network.config import GKNConfig
            from geometric_knowledge_network.vector_store import EmbeddingVectorStore

            return EmbeddingVectorStore(GKNConfig())
        from geometric_knowledge_network.vector_store import SimpleVectorStore

        return SimpleVectorStore()

    def search(self, issue: str, top_k: int | None = None) -> List[LookupResult]:
        """Return the top applicable provisions for a free-text issue/observation."""
        top_k = top_k or self.config.top_k
        # Retrieve extra chunks so we can dedup to `top_k` distinct provisions.
        hits = self.vector_store.search(issue, top_k=max(top_k * 4, top_k))

        best: dict[str, LookupResult] = {}
        for hit in hits:
            provision = self._by_id.get(hit.doc_id)
            if provision is None:
                continue
            existing = best.get(hit.doc_id)
            if existing is None or hit.score > existing.score:
                best[hit.doc_id] = LookupResult(provision=provision, score=float(hit.score), snippet=hit.text[:300])

        ranked = sorted(best.values(), key=lambda r: r.score, reverse=True)
        return ranked[:top_k]
