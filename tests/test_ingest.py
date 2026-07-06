"""Offline parser tests — synthetic inputs, no network or PDF needed."""
from __future__ import annotations

from regulus.ingest.base import Provision
from regulus.ingest.eu_ai_act import EUAIActParser
from regulus.ingest.nist_ai_rmf import NISTAIRMFParser

_EU_HTML = """
<html><body>
<p class="oj-ti-art">Article 5</p>
<p class="oj-sti-art">Prohibited AI practices`</p>
<p class="oj-normal">The following AI practices shall be prohibited: real-time remote biometric identification.</p>
<p class="oj-ti-art">Article 6</p>
<p class="oj-sti-art">Classification rules for high-risk AI systems</p>
<p class="oj-normal">An AI system shall be considered high-risk where it meets the conditions.</p>
<p class="oj-ti-annex">ANNEX I</p>
<p class="oj-normal">This annex text must not be parsed as an article.</p>
</body></html>
"""

_NIST_TEXT = (
    "Appendix A. GOVERN 1.1: Legal and regulatory requirements involving AI are understood and documented. "
    "MEASURE 2.11: Fairness and bias are evaluated and results are documented. "
    "MANAGE 1.1: Determination is made as to whether the AI system achieves its intended purposes."
)


def test_eu_ai_act_parser_basic():
    provs = EUAIActParser().parse(_EU_HTML.encode("utf-8"))
    ids = {p.provision_id for p in provs}
    assert ids == {"Article 5", "Article 6"}  # annex excluded
    a5 = next(p for p in provs if p.provision_id == "Article 5")
    assert a5.title == "Prohibited AI practices"  # trailing backtick stripped
    assert "biometric" in a5.text
    assert a5.source_url.endswith("#art_5")
    assert a5.framework_id == "eu_ai_act"


def test_nist_parser_text_mode():
    provs = NISTAIRMFParser().parse(_NIST_TEXT)
    ids = {p.provision_id for p in provs}
    assert {"GOVERN 1.1", "MEASURE 2.11", "MANAGE 1.1"} <= ids
    measure = next(p for p in provs if p.provision_id == "MEASURE 2.11")
    assert measure.text.startswith("Fairness")  # leading colon stripped
    assert measure.framework_name == "NIST AI RMF 1.0"


def test_provision_helpers():
    p = Provision(
        framework_id="eu_ai_act",
        framework_name="EU AI Act",
        provision_id="Article 5",
        title="Prohibited AI practices",
        text="...",
        source_url="https://example/#art_5",
    )
    assert p.unique_id() == "eu_ai_act::article_5"
    assert "EU AI Act, Article 5" in p.citation()
    assert p.full_text().startswith("EU AI Act, Article 5")
