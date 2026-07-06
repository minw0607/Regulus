"""Parser for the NIST AI Risk Management Framework 1.0 (NIST AI 100-1) PDF.

The framework is organized into four functions — GOVERN, MAP, MEASURE, MANAGE —
each with numbered categories and subcategories (e.g. ``MEASURE 2.11``). Those
subcategory codes appear in the document (Appendix A tables), so we extract text,
split on the subcategory codes, and emit one Provision per subcategory. If PDF
text extraction is too degraded to find subcategories, we fall back to
function-level sections so ingestion still produces usable, cited units.
"""
from __future__ import annotations

import re
from typing import List

from .base import Provision

FRAMEWORK_ID = "nist_ai_rmf"
FRAMEWORK_NAME = "NIST AI RMF 1.0"
BASE_URL = "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf"

_FUNCTIONS = ("GOVERN", "MAP", "MEASURE", "MANAGE")
_SUBCATEGORY = re.compile(rf"\b({'|'.join(_FUNCTIONS)})\s+(\d+)\.(\d+)\b")


def _pdf_to_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pypdf is required to parse the NIST AI RMF PDF (pip install pypdf).") from exc

    import io

    reader = PdfReader(io.BytesIO(raw))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


class NISTAIRMFParser:
    def parse(self, raw: bytes, source_url: str = BASE_URL) -> List[Provision]:
        # bytes -> extract from PDF; str -> already plain text (e.g. tests / cached .txt)
        text = raw if isinstance(raw, str) else _pdf_to_text(raw)
        text = re.sub(r"[ \t]+", " ", text)

        matches = list(_SUBCATEGORY.finditer(text))
        provisions: List[Provision] = []
        seen: set[str] = set()
        for i, match in enumerate(matches):
            code = f"{match.group(1)} {match.group(2)}.{match.group(3)}"
            if code in seen:
                continue
            seen.add(code)
            body = text[match.end(): matches[i + 1].start()] if i + 1 < len(matches) else text[match.end():]
            body = body.strip().lstrip(":").strip()[:1200]
            if len(body) < 40:
                continue
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=code,
                    title=match.group(1).title() + " function",
                    text=body,
                    source_url=source_url,
                    section_path=[FRAMEWORK_NAME, match.group(1), code],
                )
            )

        if provisions:
            return provisions
        return self._function_level_fallback(text, source_url)

    def _function_level_fallback(self, text: str, source_url: str) -> List[Provision]:
        provisions: List[Provision] = []
        positions = [(m.group(0), m.start()) for m in re.finditer(rf"\b({'|'.join(_FUNCTIONS)})\b", text)]
        for i, (name, start) in enumerate(positions[:4]):
            end = positions[i + 1][1] if i + 1 < len(positions) else len(text)
            body = text[start:end].strip()[:2000]
            if len(body) < 80:
                continue
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=f"{name} function",
                    title=f"{name.title()} function",
                    text=body,
                    source_url=source_url,
                    section_path=[FRAMEWORK_NAME, name],
                )
            )
        return provisions
