"""Parser for MITRE ATLAS (Adversarial Threat Landscape for AI Systems).

Source: the machine-readable ``ATLAS.yaml`` distributed from
https://github.com/mitre-atlas/atlas-data (single file; tactics, techniques,
mitigations). ATLAS is the *threat layer* of the Regulus knowledge network:

- **techniques** (e.g. ``AML.T0051`` LLM Prompt Injection) become Provisions —
  what an attack *is*;
- **mitigations** (e.g. ``AML.M0004`` Restrict Number of AI Model Queries) become
  Provisions — what *stops* it;
- the mitigation→technique links that ship **in the ATLAS data itself** (each
  with a per-link ``use`` rationale) are exported as authoritative crosswalk rows
  by :func:`build_crosswalk_rows` — no curation needed, and every edge carries
  MITRE's own explanation of *why* the two are related. Technique→parent
  ``specializes`` links are exported the same way.

Parsing needs ``pyyaml``; without it the loader falls back to the committed
snapshot (same pattern as the NIST PDFs and pypdf).
"""
from __future__ import annotations

from typing import Dict, List

from .base import Provision

FRAMEWORK_ID = "mitre_atlas"
FRAMEWORK_NAME = "MITRE ATLAS"
BASE_URL = "https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/ATLAS.yaml"
SITE = "https://atlas.mitre.org"


def _load_yaml(raw: bytes) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pyyaml is required to parse ATLAS.yaml (pip install pyyaml).") from exc
    return yaml.safe_load(raw)


def _matrix(data: dict) -> dict:
    return data["matrices"][0]


class MitreAtlasParser:
    def parse(self, raw: bytes, source_url: str = BASE_URL) -> List[Provision]:
        data = _load_yaml(raw)
        m = _matrix(data)
        tactic_names: Dict[str, str] = {t["id"]: t["name"] for t in m.get("tactics", [])}

        provisions: List[Provision] = []
        for t in m.get("techniques", []):
            tid, name = t["id"], t["name"]
            tactics = [tactic_names.get(x, x) for x in t.get("tactics", [])]
            tactic_line = f"Tactic: {', '.join(tactics)}. " if tactics else ""
            maturity = t.get("maturity", "")
            mat_line = f"Maturity: {maturity}. " if maturity else ""
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=tid,
                    title=name,
                    text=f"{tactic_line}{mat_line}{(t.get('description') or '').strip()}",
                    source_url=f"{SITE}/techniques/{tid}",
                    section_path=[FRAMEWORK_NAME, "Technique", *tactics[:1], tid],
                )
            )
        for mit in m.get("mitigations", []):
            mid, name = mit["id"], mit["name"]
            cats = mit.get("category") or []
            cat_line = f"Category: {', '.join(cats)}. " if cats else ""
            provisions.append(
                Provision(
                    framework_id=FRAMEWORK_ID,
                    framework_name=FRAMEWORK_NAME,
                    provision_id=mid,
                    title=name,
                    text=f"{cat_line}{(mit.get('description') or '').strip()}",
                    source_url=f"{SITE}/mitigations/{mid}",
                    section_path=[FRAMEWORK_NAME, "Mitigation", mid],
                )
            )
        return provisions


def build_crosswalk_rows(raw: bytes) -> List[dict]:
    """Authoritative intra-ATLAS edges, straight from the ATLAS data.

    - mitigation --mitigates--> technique, with MITRE's per-link ``use`` text as
      the rationale (the *signal* explaining why the pair is connected);
    - sub-technique --specializes--> parent technique.
    """
    data = _load_yaml(raw)
    m = _matrix(data)
    version = data.get("version", "")
    src = f"MITRE ATLAS v{version} data (authoritative mitigation-to-technique mapping)"
    rows: List[dict] = []
    for mit in m.get("mitigations", []):
        for link in mit.get("techniques", []):
            use = " ".join(str(link.get("use", "")).split())[:240]
            rows.append({
                "source_framework": FRAMEWORK_ID,
                "source_provision": mit["id"],
                "target_framework": FRAMEWORK_ID,
                "target_provision": link["id"],
                "relation": "mitigates",
                "rationale": use or f"{mit['name']} mitigates this technique.",
                "source": src,
            })
    for t in m.get("techniques", []):
        parent = t.get("specializes")
        if parent:
            rows.append({
                "source_framework": FRAMEWORK_ID,
                "source_provision": t["id"],
                "target_framework": FRAMEWORK_ID,
                "target_provision": parent,
                "relation": "specializes",
                "rationale": f"{t['name']} is an ATLAS sub-technique of {parent}.",
                "source": f"MITRE ATLAS v{version} data (technique hierarchy)",
            })
    return rows
