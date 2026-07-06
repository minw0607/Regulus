"""Registry of supported governance / regulatory frameworks.

Each entry knows where to fetch the source, how to parse it, and its licensing.
Frameworks whose text is not freely fetchable (e.g. paywalled ISO standards, or
sites that block automated access) are registered as ``fetchable=False`` so the
loader skips them gracefully rather than failing the whole ingest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .ingest.base import FrameworkParser
from .ingest.eu_ai_act import EUAIActParser
from .ingest.nist_ai_rmf import NISTAIRMFParser


@dataclass(frozen=True)
class FrameworkSource:
    framework_id: str
    name: str
    url: str
    cache_filename: str
    parser: FrameworkParser
    license: str
    fetchable: bool = True
    note: str = ""


FRAMEWORK_SOURCES: Dict[str, FrameworkSource] = {
    "eu_ai_act": FrameworkSource(
        framework_id="eu_ai_act",
        name="EU AI Act",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689",
        cache_filename="eu_ai_act.html",
        parser=EUAIActParser(),
        license="© European Union, 1998-2024. Reuse authorised under the EUR-Lex reuse policy with attribution.",
    ),
    "nist_ai_rmf": FrameworkSource(
        framework_id="nist_ai_rmf",
        name="NIST AI RMF 1.0",
        url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        cache_filename="nist_ai_rmf.pdf",
        parser=NISTAIRMFParser(),
        license="NIST publication — U.S. Government work, not subject to copyright in the United States.",
    ),
    # Fetch-if-available / manual sources (registered for the roadmap; the loader
    # skips them cleanly if unreachable or without a parser yet).
    "fed_sr_11_7": FrameworkSource(
        framework_id="fed_sr_11_7",
        name="Federal Reserve SR 11-7 (Model Risk Management)",
        url="https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm",
        cache_filename="fed_sr_11_7.html",
        parser=EUAIActParser(),  # placeholder; a dedicated parser is future work
        license="U.S. Government work (Federal Reserve).",
        fetchable=False,
        note="Federal Reserve site blocks automated fetches on some paths; add a dedicated parser + manual download.",
    ),
    "iso_42001": FrameworkSource(
        framework_id="iso_42001",
        name="ISO/IEC 42001:2023 (AI management system)",
        url="",
        cache_filename="iso_42001.txt",
        parser=EUAIActParser(),  # placeholder
        license="ISO copyright — not freely redistributable; reference only.",
        fetchable=False,
        note="Paywalled. Reference the clause structure; do not redistribute text.",
    ),
}


def fetchable_sources() -> Dict[str, FrameworkSource]:
    return {fid: src for fid, src in FRAMEWORK_SOURCES.items() if src.fetchable and src.url}
