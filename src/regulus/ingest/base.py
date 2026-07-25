from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import List, Protocol


@dataclass
class Provision:
    """A single, citable unit of a regulatory framework.

    A Provision is the atomic retrieval + graph unit in Regulus: an article,
    control, requirement, or subcategory that can be applied to an issue and
    cross-referenced against other frameworks. Provenance (``source_url``,
    ``section_path``) is mandatory — a governance tool must always cite its source.
    """

    framework_id: str          # e.g. "eu_ai_act"
    framework_name: str        # e.g. "EU AI Act"
    provision_id: str          # e.g. "Article 5"
    title: str                 # e.g. "Prohibited AI practices"
    text: str                  # normative text of the provision
    source_url: str            # citable source (anchored where possible)
    section_path: List[str] = field(default_factory=list)  # e.g. ["EU AI Act", "Article 5"]

    def unique_id(self) -> str:
        return provision_uid(self.framework_id, self.provision_id)

    def citation(self) -> str:
        return f"{self.framework_name}, {self.provision_id}" + (f" — {self.title}" if self.title else "")

    def full_text(self) -> str:
        """Text used for embedding/indexing — includes the citation header so the
        framework and provision id contribute to the semantic match."""
        header = self.citation()
        return f"{header}\n\n{self.text}".strip()

    def text_hash(self) -> str:
        return sha256(self.full_text().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "framework_id": self.framework_id,
            "framework_name": self.framework_name,
            "provision_id": self.provision_id,
            "title": self.title,
            "text": self.text,
            "source_url": self.source_url,
            "section_path": list(self.section_path),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Provision":
        return cls(
            framework_id=data["framework_id"],
            framework_name=data["framework_name"],
            provision_id=data["provision_id"],
            title=data.get("title", ""),
            text=data["text"],
            source_url=data.get("source_url", ""),
            section_path=list(data.get("section_path", [])),
        )

    @staticmethod
    def _slug(value: str) -> str:
        return slug(value)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def provision_uid(framework_id: str, provision_id: str) -> str:
    """Stable graph-node id for a provision — used by both Provision and crosswalks."""
    return f"{slug(framework_id)}::{slug(provision_id)}"


class FrameworkParser(Protocol):
    """Parses raw framework content (HTML/PDF/text) into Provision records."""

    def parse(self, raw: bytes, source_url: str) -> List[Provision]:  # pragma: no cover - interface
        ...


def pdf_to_text(raw: bytes) -> str:
    """Extract text from a PDF byte string (requires pypdf)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pypdf is required to parse this PDF (pip install pypdf).") from exc

    import io

    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def strip_html(fragment: str) -> str:
    """Remove tags and collapse whitespace from an HTML fragment."""
    import html

    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
