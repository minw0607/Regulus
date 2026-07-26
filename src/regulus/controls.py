"""A small, curated control/mitigant library keyed to the risk taxonomy.

These are **pre-built rules** (deterministic and reproducible), not LLM output:
each of the seven NIST trustworthiness risk categories maps to a control
objective and a few example control activities. They give the assessment a
stable "what should we do" column that does not vary run-to-run — the LLM
narrative (interpret.py) then adds scenario-specific nuance on top.

This is deliberately framework-neutral: the *provisions* say what is required;
these controls say, in plain governance language, how a team typically satisfies
that class of requirement. Treat them as a starting checklist, not authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .risk import RISK_BY_ID


@dataclass(frozen=True)
class Control:
    risk_id: str
    objective: str          # the control objective (one line)
    activities: tuple       # example control activities

    @property
    def risk_name(self) -> str:
        rc = RISK_BY_ID.get(self.risk_id)
        return rc.name if rc else self.risk_id


CONTROL_LIBRARY: Dict[str, Control] = {
    "valid_reliable": Control(
        "valid_reliable",
        "Establish that the system performs accurately and reliably for its intended use before and after deployment.",
        ("Define acceptance criteria and validate against them on representative data",
         "Systematic (not anecdotal) pre-deployment testing on high-impact cases",
         "Ongoing performance monitoring and drift detection in production"),
    ),
    "safe": Control(
        "safe",
        "Ensure the system does not lead to unacceptable harm under defined conditions of use.",
        ("Hazard/impact analysis for foreseeable misuse and failure modes",
         "Fail-safe behaviour and defined operating limits",
         "Incident-response plan and kill-switch / rollback procedures"),
    ),
    "secure_resilient": Control(
        "secure_resilient",
        "Protect the system against adversarial attack and unexpected conditions, and recover gracefully.",
        ("Threat modelling incl. adversarial/prompt-injection and data-poisoning",
         "Security testing and access controls over models and data",
         "Resilience/continuity testing and monitoring"),
    ),
    "accountable_transparent": Control(
        "accountable_transparent",
        "Make information and responsibility available across the lifecycle, with records that support audit.",
        ("Assign clear ownership/accountability for the system",
         "Automatic logging and record-keeping of inputs, outputs and sources",
         "Disclose AI use to affected people and provide transparency documentation"),
    ),
    "explainable_interpretable": Control(
        "explainable_interpretable",
        "Ensure the mechanisms and meaning of outputs can be explained and interpreted for the audience.",
        ("Produce and document explanations appropriate to the decision's impact",
         "Capture the evidence/sources behind each output",
         "Validate explanation fidelity and communicate limitations"),
    ),
    "privacy_enhanced": Control(
        "privacy_enhanced",
        "Safeguard privacy values such as confidentiality, anonymity and data minimisation.",
        ("Data protection / DPIA and lawful-basis review",
         "Minimise, de-identify and access-control personal data",
         "Privacy-enhancing techniques and retention limits"),
    ),
    "fair_bias_managed": Control(
        "fair_bias_managed",
        "Address equality/equity concerns and manage harmful bias across groups.",
        ("Test outcomes for disparate impact across protected groups",
         "Examine and govern training data for representativeness and bias",
         "Define and monitor fairness metrics with remediation thresholds"),
    ),
}


def control_for(risk_id: str) -> Control:
    """Return the control for a risk id, or a generic placeholder if unmapped."""
    return CONTROL_LIBRARY.get(
        risk_id,
        Control(risk_id, "Review and mitigate this risk against the cited provisions.", ()),
    )
