"""Explainable Mobile-Money & informal-SME cashflow underwriting, APR disclosure & fairness audit."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class CashflowTxn:
    month_key: str  # e.g. "2026-08"
    direction: str  # "inflow" or "outflow"
    amount_minor: int
    category: str  # "sales", "supplier", "rent", "loan_repayment", "betting", "personal"


@dataclass(frozen=True)
class LoanOffer:
    principal_minor: int
    monthly_interest_rate: float  # e.g. 0.03 for 3%/month
    upfront_fee_minor: int
    term_months: int
    currency: str = "UGX"


@dataclass(frozen=True)
class TruthInLendingDisclosure:
    principal_minor: int
    net_disbursed_minor: int
    monthly_installment_minor: int
    total_repayment_minor: int
    total_cost_of_credit_minor: int
    effective_apr_pct: float
    predatory_rate_warning: bool


@dataclass(frozen=True)
class UnderwritingDecision:
    applicant_id: str
    decision: str  # approve | counter_offer | decline
    risk_grade: str  # A | B | C | D
    months_observed: int
    median_monthly_net_minor: int
    worst_month_net_minor: int
    cashflow_cv: float  # Coefficient of variation across monthly inflows
    betting_outflow_pct: float
    dscr_median: float
    dscr_stress: float  # DSCR on worst observed month
    max_safe_principal_minor: int
    reason_codes: tuple[str, ...]
    disclosure: TruthInLendingDisclosure


@dataclass(frozen=True)
class FairnessAuditReport:
    group_approval_rates: dict[str, float]
    min_adverse_impact_ratio: float
    passes_four_fifths_rule: bool
    flagged_groups: tuple[str, ...]


def compute_truth_in_lending(offer: LoanOffer, *, apr_warning_cap_pct: float = 60.0) -> TruthInLendingDisclosure:
    """Compute exact amortized installment, net disbursement, and true annualized effective APR."""
    if offer.principal_minor <= 0 or offer.term_months <= 0 or offer.monthly_interest_rate < 0:
        raise ValueError("Invalid loan offer parameters")

    r = offer.monthly_interest_rate
    n = offer.term_months
    if r == 0.0:
        pmt = math.ceil(offer.principal_minor / n)
    else:
        pmt = math.ceil(offer.principal_minor * (r * (1.0 + r) ** n) / (((1.0 + r) ** n) - 1.0))

    total_repay = pmt * n
    net_disbursed = max(1, offer.principal_minor - max(0, offer.upfront_fee_minor))
    total_cost = max(0, total_repay - net_disbursed)

    # Bisection solve for exact monthly IRR where sum(pmt / (1+i)^t) == net_disbursed
    lo, hi = 0.0, 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        pv = sum(pmt / ((1.0 + mid) ** t) for t in range(1, n + 1))
        if pv > net_disbursed:
            lo = mid
        else:
            hi = mid
    monthly_irr = 0.5 * (lo + hi)
    effective_apr = round(((1.0 + monthly_irr) ** 12 - 1.0) * 100.0, 2)

    return TruthInLendingDisclosure(
        principal_minor=offer.principal_minor,
        net_disbursed_minor=net_disbursed,
        monthly_installment_minor=pmt,
        total_repayment_minor=total_repay,
        total_cost_of_credit_minor=total_cost,
        effective_apr_pct=effective_apr,
        predatory_rate_warning=(effective_apr > apr_warning_cap_pct),
    )


def underwrite_cashflow(
    applicant_id: str,
    transactions: list[CashflowTxn],
    offer: LoanOffer,
    *,
    min_dscr: float = 1.50,
    max_betting_pct: float = 10.0,
) -> UnderwritingDecision:
    """Evaluate informal-SME / Mobile-Money cashflows transparently without black-box scoring."""
    disclosure = compute_truth_in_lending(offer)
    inflows: dict[str, int] = defaultdict(int)
    outflows: dict[str, int] = defaultdict(int)
    debt_service: dict[str, int] = defaultdict(int)
    total_outflow = 0
    betting_outflow = 0

    for tx in transactions:
        if tx.amount_minor < 0:
            raise ValueError("Transaction amount_minor must be non-negative")
        if tx.direction == "inflow":
            inflows[tx.month_key] += tx.amount_minor
        else:
            outflows[tx.month_key] += tx.amount_minor
            total_outflow += tx.amount_minor
            if tx.category == "loan_repayment":
                debt_service[tx.month_key] += tx.amount_minor
            if tx.category == "betting":
                betting_outflow += tx.amount_minor

    months = sorted(set(inflows.keys()) | set(outflows.keys()))
    reasons: list[str] = []
    if len(months) < 3:
        reasons.append(f"THIN_FILE: only {len(months)} month(s) observed (minimum 3 recommended)")

    monthly_in = [inflows[m] for m in months]
    # Net cashflow available BEFORE existing debt service
    monthly_net_pre_debt = [inflows[m] - (outflows[m] - debt_service[m]) for m in months]
    monthly_existing_debt = [debt_service[m] for m in months]

    sorted_net = sorted(monthly_net_pre_debt) if monthly_net_pre_debt else [0]
    med_net = sorted_net[len(sorted_net) // 2]
    worst_net = sorted_net[0]
    med_existing_debt = sorted(monthly_existing_debt)[len(monthly_existing_debt) // 2] if monthly_existing_debt else 0

    if len(monthly_in) >= 2 and sum(monthly_in) > 0:
        mu = sum(monthly_in) / len(monthly_in)
        sd = math.sqrt(sum((x - mu) ** 2 for x in monthly_in) / (len(monthly_in) - 1))
        cv = sd / mu
    else:
        cv = 1.0

    betting_pct = (betting_outflow / total_outflow * 100.0) if total_outflow > 0 else 0.0
    total_debt_obligation = med_existing_debt + disclosure.monthly_installment_minor
    dscr_med = (med_net / total_debt_obligation) if total_debt_obligation > 0 else 0.0
    dscr_stress = (worst_net / total_debt_obligation) if total_debt_obligation > 0 else 0.0

    # Compute maximum safe monthly installment at min_dscr
    max_safe_pmt = max(0, int((med_net / min_dscr) - med_existing_debt))
    if offer.monthly_interest_rate == 0.0:
        max_safe_principal = max_safe_pmt * offer.term_months
    else:
        r = offer.monthly_interest_rate
        n = offer.term_months
        annuity_factor = (1.0 - (1.0 + r) ** (-n)) / r
        max_safe_principal = int(max_safe_pmt * annuity_factor)

    if betting_pct > max_betting_pct:
        reasons.append(f"HIGH_BETTING_DRAIN: {betting_pct:.1f}% of outflows spent on betting")
    if dscr_med < min_dscr:
        reasons.append(f"LOW_DSCR: median DSCR {dscr_med:.2f} < {min_dscr:.2f} affordability floor")
    if dscr_stress < 1.0:
        reasons.append(f"SEASONAL_STRESS_DEFICIT: worst-month DSCR {dscr_stress:.2f} < 1.00")
    if cv > 0.60:
        reasons.append(f"HIGH_REVENUE_VOLATILITY: inflow CV={cv:.2f}")
    if disclosure.predatory_rate_warning:
        reasons.append(
            f"HIGH_APR_WARNING: effective APR {disclosure.effective_apr_pct}% exceeds consumer protection cap"
        )

    if len(months) < 3 or betting_pct > max_betting_pct or med_net <= 0:
        decision, grade = "decline", "D"
    elif dscr_med >= min_dscr and dscr_stress >= 1.05:
        decision = "approve"
        grade = "A" if (dscr_med >= 2.2 and cv <= 0.35) else "B"
    elif max_safe_principal >= int(offer.principal_minor * 0.40):
        decision, grade = "counter_offer", "C"
    else:
        decision, grade = "decline", "D"

    return UnderwritingDecision(
        applicant_id=applicant_id,
        decision=decision,
        risk_grade=grade,
        months_observed=len(months),
        median_monthly_net_minor=med_net,
        worst_month_net_minor=worst_net,
        cashflow_cv=round(cv, 3),
        betting_outflow_pct=round(betting_pct, 2),
        dscr_median=round(dscr_med, 2),
        dscr_stress=round(dscr_stress, 2),
        max_safe_principal_minor=max_safe_principal,
        reason_codes=tuple(reasons),
        disclosure=disclosure,
    )


def audit_disparate_impact(outcomes: list[tuple[str, bool]]) -> FairnessAuditReport:
    """Audit portfolio credit decisions under the 4/5ths (80%) adverse-impact fairness rule."""
    totals: dict[str, int] = defaultdict(int)
    approvals: dict[str, int] = defaultdict(int)
    for group, approved in outcomes:
        totals[group] += 1
        if approved:
            approvals[group] += 1

    rates = {g: round(approvals[g] / totals[g], 4) for g in sorted(totals) if totals[g] > 0}
    if len(rates) < 2 or max(rates.values()) == 0.0:
        return FairnessAuditReport(rates, 1.0, True, ())

    ref_rate = max(rates.values())
    flagged = tuple(g for g, rate in rates.items() if (rate / ref_rate) < 0.80)
    min_ratio = round(min(rates.values()) / ref_rate, 4)
    return FairnessAuditReport(
        group_approval_rates=rates,
        min_adverse_impact_ratio=min_ratio,
        passes_four_fifths_rule=(min_ratio >= 0.80),
        flagged_groups=flagged,
    )
