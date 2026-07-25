"""Parser for the OECD AI Principles (Recommendation OECD/LEGAL/0449).

The recommendation numbers its items ``1.1``–``1.5`` (values-based principles for
responsible stewardship of trustworthy AI) and ``2.1``–``2.5`` (recommendations to
policy makers). We split the PDF text on those numbered headings.
"""
from __future__ import annotations

import re
from typing import List

from .base import Provision, pdf_to_text

FRAMEWORK_ID = "oecd_ai"
FRAMEWORK_NAME = "OECD AI Principles"
BASE_URL = "https://legalinstruments.oecd.org/api/print?ids=648&lang=en"

# A numbered heading: "1.1. Inclusive growth, ...". Section 1 = principles, 2 = recommendations.
_HEADING = re.compile(r"\b([12])\.([1-5])\.\s+([A-Z][A-Za-z][^\n]{4,90})")


class OECDAIParser:
    def parse(self, raw: bytes, source_url: str = BASE_URL) -> List[Provision]:
        text = raw if isinstance(raw, str) else pdf_to_text(raw)
        text = re.sub(r"[ \t]+", " ", text)

        # Start after the "Principles for responsible stewardship" header to skip the preamble.
        anchor = text.find("Principles for responsible")
        body_text = text[anchor:] if anchor != -1 else text

        matches = list(_HEADING.finditer(body_text))
        provisions: List[Provision] = []
        seen: set[str] = set()
        for i, m in enumerate(matches):
            num = f"{m.group(1)}.{m.group(2)}"
            if num in seen:
                continue
            seen.add(num)
            title = m.group(3).strip().rstrip(".")
            seg = body_text[m.end(): matches[i + 1].start()] if i + 1 < len(matches) else body_text[m.end():]
            body = re.sub(r"\s+", " ", seg).strip()[:1200]
            if len(body) < 30:
                continue
            kind = "Principle" if m.group(1) == "1" else "Recommendation"
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=f"{kind} {num}",
                    title=title,
                    text=body,
                    source_url=source_url,
                    section_path=[FRAMEWORK_NAME, f"{kind} {num}"],
                )
            )
        return provisions
