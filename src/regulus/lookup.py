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

# The corpus has two layers: what the LAW/GUIDANCE requires, and what the THREAT
# knowledge says about attacks and controls. Similarity alone tends to cluster
# hits inside one layer (a security scenario pulls only OWASP/ATLAS; a bias
# scenario only regulation). Layer-aware retrieval keeps both anchors in view.
LAYER_BY_FRAMEWORK = {
    "eu_ai_act": "regulatory",
    "nist_ai_rmf": "regulatory",
    "nist_ai_600_1": "regulatory",
    "oecd_ai": "regulatory",
    "iso_42001": "regulatory",
    "fed_sr_26_2": "regulatory",
    "mitre_atlas": "threat",
    "owasp_llm_top10": "threat",
}


def framework_layer(framework_id: str) -> str:
    return LAYER_BY_FRAMEWORK.get(framework_id, "regulatory")


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
        # Cache of raw store hits per (query, pool size). Cloud embedding endpoints
        # do not return bit-identical vectors for the same input on every call, so
        # re-embedding a query mid-review could reorder near-tied provisions. One
        # embedding per distinct query keeps a session's evidence identical — and
        # cuts API calls when the same scenario is assessed repeatedly.
        self._hits_cache: dict[tuple[str, int], list] = {}

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
        """Return the top applicable provisions for a free-text issue/observation.

        Layer-aware (when enabled and the corpus spans both layers): if the plain
        top-k all come from one layer (regulatory vs threat) and the other layer
        has a candidate scoring at least half the top score, the last slot is
        given to that candidate — so an assessment always sees both what the law
        requires and what the threat knowledge says, when both are relevant.
        Deterministic: same query + store ⇒ same result."""
        top_k = top_k or self.config.top_k
        # Retrieve extra chunks so we can dedup to `top_k` distinct provisions.
        pool = max(top_k * 6, top_k)
        cache_key = (issue, pool)
        hits = self._hits_cache.get(cache_key)
        if hits is None:
            hits = self.vector_store.search(issue, top_k=pool)
            self._hits_cache[cache_key] = hits

        best: dict[str, LookupResult] = {}
        for hit in hits:
            provision = self._by_id.get(hit.doc_id)
            if provision is None:
                continue
            existing = best.get(hit.doc_id)
            if existing is None or hit.score > existing.score:
                best[hit.doc_id] = LookupResult(provision=provision, score=float(hit.score), snippet=hit.text[:300])

        # Deterministic ranking: embedding inference (especially local, CPU) can
        # produce ~1e-7 floating-point noise between runs, which would flip the
        # order of near-tied provisions. Rank on the score rounded to 6 dp with
        # the provision uid as a stable tie-break, so the same query + store
        # yields the same list on every run.
        ranked = sorted(best.values(), key=lambda r: (-round(r.score, 6), r.provision.unique_id()))
        selected = ranked[:top_k]

        if getattr(self.config, "layer_aware", True) and len(selected) == top_k and top_k >= 2:
            corpus_layers = {framework_layer(p.framework_id) for p in self._by_id.values()}
            selected_layers = {framework_layer(r.provision.framework_id) for r in selected}
            missing = corpus_layers - selected_layers
            if missing:
                layer = missing.pop()
                threshold = round(0.5 * round(selected[0].score, 6), 6)
                candidate = next(
                    (r for r in ranked[top_k:]
                     if framework_layer(r.provision.framework_id) == layer and round(r.score, 6) >= threshold),
                    None,
                )
                if candidate is not None:
                    selected = selected[:-1] + [candidate]
        return selected
