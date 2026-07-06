"""Risk / trustworthiness taxonomy and a lightweight provision -> risk tagger.

The taxonomy follows the seven characteristics of trustworthy AI in the NIST AI
RMF 1.0 (§3). Risk tags on provisions are produced by keyword matching and are
therefore *derived, low-confidence* signals (edge attribute ``method="keyword"``)
— intended for navigation, not as authoritative classifications. Curated tags can
override them later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .ingest.base import Provision


@dataclass(frozen=True)
class RiskCategory:
    risk_id: str
    name: str
    description: str
    aliases: Tuple[str, ...]


# NIST AI RMF 1.0, §3 "Characteristics of trustworthy AI systems".
RISK_TAXONOMY: List[RiskCategory] = [
    RiskCategory("valid_reliable", "Valid and reliable",
                 "The system performs accurately and reliably for its intended use.",
                 ("accuracy", "accurate", "reliable", "reliability", "performance", "robust", "robustness")),
    RiskCategory("safe", "Safe",
                 "The system does not, under defined conditions, lead to unacceptable harm.",
                 ("safety", "safe", "harm", "physical harm", "health")),
    RiskCategory("secure_resilient", "Secure and resilient",
                 "The system withstands adversarial attacks and unexpected conditions.",
                 ("security", "cybersecurity", "secure", "resilience", "resilient", "adversarial", "attack")),
    RiskCategory("accountable_transparent", "Accountable and transparent",
                 "Information and responsibility are available across the AI lifecycle.",
                 ("transparency", "transparent", "accountability", "accountable", "documentation", "record-keeping", "logging", "traceability")),
    RiskCategory("explainable_interpretable", "Explainable and interpretable",
                 "The mechanisms and meaning of outputs can be explained and interpreted.",
                 ("explainability", "explainable", "interpretability", "interpretable", "explanation")),
    RiskCategory("privacy_enhanced", "Privacy-enhanced",
                 "Privacy values such as anonymity and confidentiality are safeguarded.",
                 ("privacy", "personal data", "data protection", "confidentiality", "anonymity")),
    RiskCategory("fair_bias_managed", "Fair — with harmful bias managed",
                 "Concerns for equality and equity are addressed and harmful bias is managed.",
                 ("fairness", "fair", "bias", "biases", "discrimination", "discriminatory", "equity", "protected", "demographic")),
]

RISK_BY_ID = {rc.risk_id: rc for rc in RISK_TAXONOMY}


def tag_provision_risks(
    provision: Provision,
    taxonomy: List[RiskCategory] | None = None,
    max_tags: int = 3,
) -> List[str]:
    """Return up to ``max_tags`` risk_ids best supported by the provision text.

    Each risk is scored by how many of its distinct aliases appear (whole-word
    match); the strongest are kept. Keyword-derived and low-confidence by design.
    """
    import re

    taxonomy = taxonomy or RISK_TAXONOMY
    text = provision.full_text().lower()
    scored: List[Tuple[int, str]] = []
    for rc in taxonomy:
        hits = sum(1 for alias in rc.aliases if re.search(r"\b" + re.escape(alias) + r"\b", text))
        if hits:
            scored.append((hits, rc.risk_id))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [risk_id for _, risk_id in scored[:max_tags]]
