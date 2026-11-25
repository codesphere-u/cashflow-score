"""Tests for cashflow-score DSCR underwriting, APR disclosures, betting drain, fairness & CLI."""

from __future__ import annotations

import json

import pytest

from cashflow_score import (
    CashflowTxn,
    LoanOffer,
    audit_disparate_impact,
    compute_truth_in_lending,
    underwrite_cashflow,
)
from cashflow_score.cli import main as cli_main


def test_healthy_vendor_approved_while_betting_drain_declined_and_predatory_apr_flagged() -> None:
    predatory = compute_truth_in_lending(
        LoanOffer(principal_minor=500_000, monthly_interest_rate=0.10, upfront_fee_minor=50_000, term_months=3)
    )
    assert predatory.predatory_rate_warning is True
    assert predatory.effective_apr_pct > 200.0

    healthy_txns = [
        CashflowTxn(m, "inflow", 2_000_000, "sales") for m in ("2026-08", "2026-09", "2026-10")
    ] + [
        CashflowTxn(m, "outflow", 1_100_000, "supplier") for m in ("2026-08", "2026-09", "2026-10")
    ]
    fair_offer = LoanOffer(1_200_000, 0.02, 20_000, 6)
    ok = underwrite_cashflow("APP-1", healthy_txns, fair_offer)
    assert ok.decision == "approve"
    assert ok.risk_grade in ("A", "B")
    assert ok.dscr_median >= 1.5

    betting_txns = [*healthy_txns, CashflowTxn("2026-10", "outflow", 900_000, "betting")]
    bad = underwrite_cashflow("APP-2", betting_txns, fair_offer)
    assert bad.decision == "decline"
    assert any("HIGH_BETTING_DRAIN" in r for r in bad.reason_codes)


def test_four_fifths_disparate_impact_fairness_audit() -> None:
    biased = [("urban", True)] * 9 + [("urban", False)] + [("rural", True)] * 5 + [("rural", False)] * 5
    rep = audit_disparate_impact(biased)
    assert rep.passes_four_fifths_rule is False
    assert "rural" in rep.flagged_groups


def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "approve"
