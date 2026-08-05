"""Offline tests for the threat-layer frameworks (MITRE ATLAS, OWASP LLM Top 10)."""
from __future__ import annotations

import json
from pathlib import Path

from regulus.config import RegulusConfig
from regulus.ingest.base import Provision
from regulus.ingest.owasp_llm import OWASPLLMParser

REPO = Path(__file__).resolve().parents[1]

_OWASP_SAMPLE = """## LLM01:2025 Prompt Injection

### Description

A Prompt Injection Vulnerability occurs when user prompts alter the LLM's behavior in unintended ways.

### Prevention and Mitigation Strategies

1. Constrain model behavior with strict system prompts.
2. Validate output formats.

### Related Frameworks

- Some other section that should not leak in wholesale.

## LLM02:2025 Sensitive Information Disclosure

### Description

Sensitive information can be revealed through LLM output, exposing personal data or credentials to attackers.

### Prevention and Mitigation Strategies

1. Sanitize training data.
"""


def test_owasp_parser_extracts_risks_with_prevention():
    provs = OWASPLLMParser().parse(_OWASP_SAMPLE.encode())
    assert [p.provision_id for p in provs] == ["LLM01", "LLM02"]
    p1 = provs[0]
    assert p1.title == "Prompt Injection"
    assert "unintended ways" in p1.text
    assert "Prevention and mitigation strategies:" in p1.text
    assert "Constrain model behavior" in p1.text
    assert p1.framework_id == "owasp_llm_top10"


def test_atlas_snapshot_has_techniques_mitigations_and_agentic_coverage():
    snap = json.loads((REPO / "data/snapshots/mitre_atlas_provisions.json").read_text())
    provs = [Provision.from_dict(r) for r in snap]
    techs = [p for p in provs if p.provision_id.startswith("AML.T")]
    mits = [p for p in provs if p.provision_id.startswith("AML.M")]
    assert len(techs) > 100 and len(mits) >= 30
    ids = {p.provision_id for p in provs}
    # LLM + agentic coverage present
    for expected in ("AML.T0051", "AML.T0054", "AML.T0070", "AML.T0080", "AML.M0029"):
        assert expected in ids
    # provenance mandatory
    assert all(p.source_url.startswith("https://atlas.mitre.org/") for p in provs)


def test_atlas_mitigation_edges_have_rationales():
    import csv

    rows = list(csv.DictReader((REPO / "data/crosswalks/atlas_mitigations.csv").open()))
    mitigates = [r for r in rows if r["relation"] == "mitigates"]
    assert len(mitigates) > 200
    # every authoritative edge carries MITRE's own per-link rationale (the signal)
    assert all(r["rationale"].strip() for r in mitigates)
    assert all("MITRE ATLAS" in r["source"] for r in mitigates)


def test_threat_layer_multihop_chain():
    """Scenario -> OWASP risk -> (equivalent) ATLAS technique -> (mitigates) control:
    the regulation-to-control chain must be walkable with per-hop signals."""
    from regulus.graph_intelligence import graph_expand
    from regulus.graph_lookup import RegulusGraphLookup
    from regulus.standards_loader import StandardsLoader

    cfg = RegulusConfig()
    cfg.retriever = "tfidf"
    provisions = StandardsLoader(cfg).load(framework_ids=["owasp_llm_top10", "mitre_atlas"])
    gl = RegulusGraphLookup(provisions, cfg)

    # top_k=1 so the OWASP risk is the only seed — the ATLAS technique and its
    # mitigations must then be reached purely by walking the graph.
    results = gl.search("user prompts alter the LLM's behavior in unintended ways (prompt injection)", top_k=1)
    assert results and results[0].provision.framework_id == "owasp_llm_top10"

    reach = graph_expand(gl, results, max_hops=2)
    reached_ids = {r.citation for r in reach}
    # 1 hop: the equivalent ATLAS technique; 2 hops: its mitigations
    assert any("AML.T0051" in c for c in reached_ids)
    two_hop_mitigations = [r for r in reach if r.hops == 2 and "AML.M" in r.citation]
    assert two_hop_mitigations
    # every hop carries a signal explaining WHY the link exists
    assert all(len(r.signals) == r.hops and all(s for s in r.signals) for r in reach)
