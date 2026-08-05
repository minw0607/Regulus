"""Parser for the OWASP Top 10 for LLM Applications 2025.

Source: the official per-risk markdown files in
https://github.com/OWASP/www-project-top-10-for-large-language-model-applications
(``2_0_vulns/LLM01_*.md`` … ``LLM10_*.md``), licensed CC BY-SA 4.0 (attribution
required, redistribution permitted).

There is no single-file distribution, so ingestion works from a *bundle*: the ten
markdown files concatenated (see :func:`refresh_bundle`, which downloads them and
writes both the cache bundle and the committed snapshot). The parser reads the
bundle; each ``## LLMxx:2025 <name>`` section becomes one Provision whose text is
the Description plus the Prevention and Mitigation Strategies — so a retrieval hit
carries both *what the risk is* and *what to do about it*.
"""
from __future__ import annotations

import re
from typing import List

from .base import Provision

FRAMEWORK_ID = "owasp_llm_top10"
FRAMEWORK_NAME = "OWASP Top 10 for LLM (2025)"
REPO_RAW = "https://raw.githubusercontent.com/OWASP/www-project-top-10-for-large-language-model-applications/main/2_0_vulns"
SITE = "https://genai.owasp.org/llm-top-10/"

FILES = [
    "LLM01_PromptInjection", "LLM02_SensitiveInformationDisclosure", "LLM03_SupplyChain",
    "LLM04_DataModelPoisoning", "LLM05_ImproperOutputHandling", "LLM06_ExcessiveAgency",
    "LLM07_SystemPromptLeakage", "LLM08_VectorAndEmbeddingWeaknesses", "LLM09_Misinformation",
    "LLM10_UnboundedConsumption",
]

_RISK_HEADER = re.compile(r"^##\s+(LLM\d{2}):2025\s+(.+?)\s*$", re.MULTILINE)


def _section(body: str, name: str) -> str:
    """Extract one `### name` section's text from a risk body."""
    m = re.search(rf"^###\s+{re.escape(name)}\s*$(.*?)(?=^###\s|\Z)", body, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


class OWASPLLMParser:
    def parse(self, raw: bytes, source_url: str = SITE) -> List[Provision]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        headers = list(_RISK_HEADER.finditer(text))
        provisions: List[Provision] = []
        for i, h in enumerate(headers):
            risk_id, name = h.group(1), h.group(2).strip()
            body = text[h.end(): headers[i + 1].start()] if i + 1 < len(headers) else text[h.end():]
            desc = _section(body, "Description")
            prevention = _section(body, "Prevention and Mitigation Strategies")
            parts = [desc]
            if prevention:
                parts.append("Prevention and mitigation strategies:\n" + prevention)
            full = re.sub(r"\n{3,}", "\n\n", "\n\n".join(p for p in parts if p)).strip()
            if len(full) < 50:
                continue
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=risk_id,
                    title=name,
                    text=full[:6000],
                    source_url=source_url,
                    section_path=[FRAMEWORK_NAME, risk_id],
                )
            )
        return provisions


def refresh_bundle(cache_path, snapshot_path=None) -> List[Provision]:
    """Download the ten official markdown files, write the concatenated bundle to
    ``cache_path``, optionally write the parsed snapshot JSON, return the provisions."""
    import json
    import urllib.request
    from pathlib import Path

    chunks = []
    for name in FILES:
        with urllib.request.urlopen(f"{REPO_RAW}/{name}.md", timeout=30) as resp:
            chunks.append(resp.read().decode("utf-8", errors="replace"))
    bundle = "\n\n".join(chunks)
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(bundle, encoding="utf-8")

    provisions = OWASPLLMParser().parse(bundle)
    if snapshot_path:
        Path(snapshot_path).write_text(
            json.dumps([p.to_dict() for p in provisions], indent=1, ensure_ascii=False), encoding="utf-8"
        )
    return provisions
