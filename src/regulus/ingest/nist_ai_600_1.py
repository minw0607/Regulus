"""Parser for the NIST AI 600-1 — Generative AI Profile (an AI RMF companion).

NIST AI 600-1 lists suggested actions for generative AI, each keyed to an AI RMF
subcategory via codes like ``GV-1.1-001``, ``MS-2.11-003``. We group the actions
by subcategory (``GV-1.1`` ...) into one provision each — a manageable set that
maps 1:1 back to the AI RMF (``GV-1.1`` -> ``GOVERN 1.1``), giving *authoritative*
crosswalks derived from NIST's own numbering.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import List

from .base import Provision, pdf_to_text

FRAMEWORK_ID = "nist_ai_600_1"
FRAMEWORK_NAME = "NIST AI 600-1 (GenAI Profile)"
BASE_URL = "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf"

FUNCTION_NAMES = {"GV": "GOVERN", "MP": "MAP", "MS": "MEASURE", "MG": "MANAGE"}
_ACTION = re.compile(r"\b(GV|MP|MS|MG)-(\d+\.\d+)-(\d+)\b")


class NISTAI600Parser:
    def parse(self, raw: bytes, source_url: str = BASE_URL) -> List[Provision]:
        text = raw if isinstance(raw, str) else pdf_to_text(raw)
        text = re.sub(r"[ \t]+", " ", text)

        matches = list(_ACTION.finditer(text))
        groups: "OrderedDict[str, list[str]]" = OrderedDict()
        for i, m in enumerate(matches):
            prefix = f"{m.group(1)}-{m.group(2)}"
            seg = text[m.end(): matches[i + 1].start()] if i + 1 < len(matches) else text[m.end():]
            groups.setdefault(prefix, []).append(seg.strip())

        provisions: List[Provision] = []
        for prefix, segs in groups.items():
            func_code, subcat = prefix.split("-")
            func = FUNCTION_NAMES[func_code]
            body = " ".join(s for s in segs if s)[:1500].strip().lstrip(":").strip()
            if len(body) < 30:
                continue
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=prefix,
                    title=f"{func} {subcat} — generative-AI suggested actions",
                    text=body,
                    source_url=source_url,
                    section_path=[FRAMEWORK_NAME, func, prefix],
                )
            )
        return provisions
