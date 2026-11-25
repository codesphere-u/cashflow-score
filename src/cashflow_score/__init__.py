"""cashflow-score — Explainable informal-SME cashflow underwriting & fairness engine."""

from cashflow_score.underwriting import (
    CashflowTxn,
    FairnessAuditReport,
    LoanOffer,
    TruthInLendingDisclosure,
    UnderwritingDecision,
    audit_disparate_impact,
    compute_truth_in_lending,
    underwrite_cashflow,
)

__version__ = "0.1.0"

__all__ = [
    "CashflowTxn",
    "FairnessAuditReport",
    "LoanOffer",
    "TruthInLendingDisclosure",
    "UnderwritingDecision",
    "__version__",
    "audit_disparate_impact",
    "compute_truth_in_lending",
    "underwrite_cashflow",
]
