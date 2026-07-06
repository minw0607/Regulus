"""Issue -> applicable provisions lookup, built on the GKN retrieval substrate.

This is the Phase-1 baseline: semantic retrieval over the provision corpus. It
converts each Provision into a GKN document, chunks + indexes it, and maps
retrieved chunks back to their provisions (with provenance). Later phases add the
regulatory knowledge graph and multi-hop crosswalk expansion on top of this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from geometric_knowledge_network.ingest import Document, DocumentIngestor

from .config import RegulusConfig
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
        self._by_id = {p.unique_id(): p for p in provisions}

        documents = [
            Document(
                doc_id=p.unique_id(),
                title=p.citation(),
                text=p.full_text(),
                source_path=p.source_url,
                text_hash=p.text_hash(),
            )
            for p in provisions
        ]
        self.chunks = DocumentIngestor().chunk_documents(
            documents, chunk_size=self.config.chunk_size, chunk_overlap=self.config.chunk_overlap
        )
        self.vector_store = self._build_vector_store()
        self.vector_store.build(self.chunks)

    def _build_vector_store(self):
        if self.config.retriever == "embedding":
            # Reuse GKN's embedding store (Azure/OpenAI or local, per GKN env vars),
            # with its faiss/openai fallbacks.
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
