"""Save an assessment to a local folder — Markdown, JSON, and CSV tables.

Governance work needs an artefact you can file, diff, and hand to an auditor.
``export_assessment`` writes, into a per-scenario timestamped folder:

- ``assessment.md``   — the full human-readable report (same as displayed)
- ``assessment.json`` — the structured record (deterministic core + LLM text)
- ``risks.csv``       — risk × relevant standards × control
- ``priority.csv``    — the graph-leverage ranking

Reproducibility note: the ``.json`` and ``.csv`` files are the deterministic core,
so two runs of the same scenario produce byte-identical tables (only the ``.md``'s
section 4 LLM prose can differ).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .assess import Assessment


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "scenario"


def export_assessment(
    assessment: "Assessment",
    out_dir: Path | str = "artifacts/assessments",
    timestamp: bool = True,
) -> Path:
    """Write the assessment to ``out_dir/<slug>[-<ts>]/`` and return that folder."""
    base = Path(out_dir)
    name = _slug(assessment.scenario)
    if timestamp:
        name = f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "assessment.md").write_text(assessment.to_markdown(), encoding="utf-8")
    (folder / "assessment.json").write_text(
        json.dumps(assessment.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    assessment.risk_table().to_csv(folder / "risks.csv", index=False)
    if assessment.priority:
        assessment.priority_table().to_csv(folder / "priority.csv", index=False)
    return folder
