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
from .ingest.nist_ai_600_1 import NISTAI600Parser
from .ingest.nist_ai_rmf import NISTAIRMFParser
from .ingest.oecd_ai import OECDAIParser


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
    # Committed snapshot of parsed provisions, used as a fallback when live
    # download/parsing is unavailable (e.g. pypdf missing). Public-domain sources only.
    snapshot_filename: str = ""


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
        snapshot_filename="nist_ai_rmf_provisions.json",  # public-domain; used if pypdf/PDF unavailable
    ),
    "nist_ai_600_1": FrameworkSource(
        framework_id="nist_ai_600_1",
        name="NIST AI 600-1 (GenAI Profile)",
        url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf",
        cache_filename="nist_ai_600_1.pdf",
        parser=NISTAI600Parser(),
        license="NIST publication — U.S. Government work, not subject to copyright in the United States.",
        snapshot_filename="nist_ai_600_1_provisions.json",
    ),
    "oecd_ai": FrameworkSource(
        framework_id="oecd_ai",
        name="OECD AI Principles",
        url="https://legalinstruments.oecd.org/api/print?ids=648&lang=en",
        cache_filename="oecd_ai_principles.pdf",
        parser=OECDAIParser(),
        license="© OECD. Recommendation OECD/LEGAL/0449; reuse under OECD terms with attribution.",
        snapshot_filename="oecd_ai_provisions.json",
    ),
    # Structure-only (paywalled): no full text, loaded from a curated reference snapshot.
    "iso_42001": FrameworkSource(
        framework_id="iso_42001",
        name="ISO/IEC 42001:2023",
        url="",
        cache_filename="iso_42001.txt",
        parser=NISTAIRMFParser(),  # unused; loaded from snapshot only
        license="ISO copyright — not freely redistributable; clause STRUCTURE referenced only.",
        fetchable=False,
        note="Paywalled. Clause structure/titles only (no normative text); see the standard.",
        snapshot_filename="iso_42001_structure.json",
    ),
    # Registered for the roadmap; needs manual sourcing (site blocks automated fetches).
    "fed_sr_26_2": FrameworkSource(
        framework_id="fed_sr_26_2",
        name="Federal Reserve SR 26-2 (Model Risk Management; supersedes SR 11-7)",
        url="",
        cache_filename="fed_sr_26_2.pdf",
        parser=NISTAIRMFParser(),  # placeholder until a source + parser are added
        license="U.S. Government work (Federal Reserve).",
        fetchable=False,
        note="Supersedes SR 11-7. federalreserve.gov blocks automated fetches — add a manual download + parser.",
    ),
}


def fetchable_sources() -> Dict[str, FrameworkSource]:
    return {fid: src for fid, src in FRAMEWORK_SOURCES.items() if src.fetchable and src.url}
