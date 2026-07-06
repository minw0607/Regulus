"""Regulatory knowledge-graph schema (node and edge types).

Defined now to anchor the design; the graph itself is built in a later phase on
top of the ingested provisions. Crosswalk edges MUST be authoritative and cited
(curated or sourced from official mappings) — never inferred by an LLM without a
source, because a governance tool that invents regulatory mappings is a liability.
"""
from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    FRAMEWORK = "Framework"          # NIST AI RMF, EU AI Act, SR 11-7, ...
    PROVISION = "Provision"          # a specific article / control / subcategory
    RISK_CATEGORY = "RiskCategory"   # fairness, robustness, transparency, model risk, ...
    ISSUE = "Issue"                  # a user-submitted observation
    GUIDANCE = "Guidance"            # interpretation / how-to
    LIFECYCLE_STAGE = "LifecycleStage"  # data, development, validation, deployment, monitoring


class EdgeType(str, Enum):
    CONTAINS = "CONTAINS"            # Framework -> Provision
    ADDRESSES = "ADDRESSES"          # Provision -> RiskCategory
    MITIGATES = "MITIGATES"          # Provision -> RiskCategory (control lens)
    CROSSWALK = "CROSSWALK"          # Provision <-> Provision (across frameworks) — CITED
    REQUIRES = "REQUIRES"            # Provision -> control / evidence / ValidationStep
    APPLIES_TO = "APPLIES_TO"        # Provision -> Issue
    CITES = "CITES"                  # Guidance/Answer -> Provision
    INTERPRETS = "INTERPRETS"        # Guidance -> Provision
