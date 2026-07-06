"""Parser for the EU AI Act (Regulation (EU) 2024/1689) from EUR-Lex HTML.

EUR-Lex serves the Official Journal HTML with stable class markers:
- ``<p class="oj-ti-art">Article N</p>``   — article number
- ``<p class="oj-sti-art">Title</p>``      — article title
- ``<p class="oj-normal">...</p>``          — normative paragraphs
- ``id="art_N"``                            — per-article anchors (for citations)

We split the document on article-title markers, take each article's span up to
the next one (stopping before the annexes), and clean the body to plain text.
"""
from __future__ import annotations

import re
from typing import List

from .base import Provision, strip_html

_ARTICLE_TITLE = re.compile(
    r'<p[^>]*class="[^"]*\boj-ti-art\b[^"]*"[^>]*>\s*Article\s+(\d+)\s*</p>',
    re.IGNORECASE,
)
_SUBTITLE = re.compile(
    r'<p[^>]*class="[^"]*\boj-sti-art\b[^"]*"[^>]*>(.*?)</p>',
    re.IGNORECASE | re.DOTALL,
)
_ANNEX_START = re.compile(r'<p[^>]*class="[^"]*\boj-ti-annex\b[^"]*"', re.IGNORECASE)

FRAMEWORK_ID = "eu_ai_act"
FRAMEWORK_NAME = "EU AI Act"
BASE_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689"


class EUAIActParser:
    def parse(self, raw: bytes, source_url: str = BASE_URL) -> List[Provision]:
        html_text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw

        # Cut off the annexes so article parsing does not run into them.
        annex = _ANNEX_START.search(html_text)
        body = html_text[: annex.start()] if annex else html_text

        matches = list(_ARTICLE_TITLE.finditer(body))
        provisions: List[Provision] = []
        for i, match in enumerate(matches):
            number = match.group(1)
            span_start = match.end()
            span_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            span = body[span_start:span_end]

            subtitle_match = _SUBTITLE.search(span)
            title = strip_html(subtitle_match.group(1)) if subtitle_match else ""
            title = re.sub(r"[\s`*‘’]+$", "", title)  # drop EUR-Lex footnote artifacts
            # Body text = everything after the subtitle (or the whole span).
            body_html = span[subtitle_match.end():] if subtitle_match else span
            text = strip_html(body_html)
            if not text:
                continue

            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=f"Article {number}",
                    title=title,
                    text=text,
                    source_url=f"{source_url}#art_{number}",
                    section_path=[FRAMEWORK_NAME, f"Article {number}"],
                )
            )
        return provisions
