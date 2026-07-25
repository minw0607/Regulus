"""Curated, cited cross-framework crosswalks.

A crosswalk links a provision in one framework to a related provision in another
(e.g. NIST AI RMF MEASURE 2.11 <-> EU AI Act Article 10). Crosswalks are loaded
from a committed CSV (``data/crosswalks/crosswalks.csv``) — they are curated and
cited, never inferred by a model at runtime.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .ingest.base import provision_uid


def _default_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "crosswalks"


@dataclass(frozen=True)
class Crosswalk:
    source_framework: str
    source_provision: str
    target_framework: str
    target_provision: str
    relation: str      # equivalent | related | supports
    rationale: str
    source: str        # citation / provenance for the mapping

    def source_uid(self) -> str:
        return provision_uid(self.source_framework, self.source_provision)

    def target_uid(self) -> str:
        return provision_uid(self.target_framework, self.target_provision)


_REQUIRED = {"source_framework", "source_provision", "target_framework", "target_provision", "relation"}


def load_crosswalks(path: Path | None = None) -> List[Crosswalk]:
    """Load crosswalks from a CSV file, or from every ``*.csv`` in the crosswalks
    directory when no explicit path is given."""
    if path is not None:
        files = [Path(path)]
    else:
        d = _default_dir()
        files = sorted(d.glob("*.csv")) if d.exists() else []

    crosswalks: List[Crosswalk] = []
    for file in files:
        if not file.exists():
            continue
        # Drop comment lines (leading '#') so the CSV can carry notes.
        lines = [ln for ln in file.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            if not row or not _REQUIRED <= {k for k, v in row.items() if v}:
                continue
            crosswalks.append(
                Crosswalk(
                    source_framework=row["source_framework"].strip(),
                    source_provision=row["source_provision"].strip(),
                    target_framework=row["target_framework"].strip(),
                    target_provision=row["target_provision"].strip(),
                    relation=row["relation"].strip() or "related",
                    rationale=(row.get("rationale") or "").strip(),
                    source=(row.get("source") or "").strip(),
                )
            )
    return crosswalks
