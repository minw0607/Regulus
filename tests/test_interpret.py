"""Offline tests for the LLM interpretation layer (context-building + dry run)."""
from __future__ import annotations

from regulus.config import RegulusConfig
from regulus.graph_lookup import RegulusGraphLookup
from regulus.interpret import RegulusInterpreter

from tests.test_graph import _corpus


def _interpreter():
    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    cfg.openai_api_key = ""  # force dry run — never call the API in tests
    gl = RegulusGraphLookup(_corpus(), cfg)
    return RegulusInterpreter(gl, cfg)


def test_build_context_is_grounded_and_cited():
    interp = _interpreter()
    context, citations = interp.build_context("model not tested for demographic bias", top_k=2)
    assert context and citations
    assert any("MEASURE 2.11" in c or "Article" in c for c in citations)
    assert "source:" in context  # every provision carries provenance


def test_interpret_dry_run_without_api_key():
    interp = _interpreter()
    result = interp.interpret("model not tested for demographic bias", top_k=2)
    assert result.answer_markdown is None       # no LLM called
    assert "OPENAI_API_KEY" in result.note or "openai" in result.note
    assert result.context and result.citations  # but the structured context is ready
