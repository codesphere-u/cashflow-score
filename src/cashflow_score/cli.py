"""CLI for cashflow-score."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from cashflow_score.underwriting import CashflowTxn, LoanOffer, underwrite_cashflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cashflow-score",
        description="Explainable informal-SME & Mobile-Money cashflow underwriting CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Underwrite a 4-month Kampala market vendor Mobile-Money statement")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        txns: list[CashflowTxn] = []
        for m, sales, stock in [
            ("2026-08", 2_400_000, 1_550_000),
            ("2026-09", 2_650_000, 1_700_000),
            ("2026-10", 2_100_000, 1_350_000),
            ("2026-11", 2_550_000, 1_600_000),
        ]:
            txns.append(CashflowTxn(m, "inflow", sales, "sales"))
            txns.append(CashflowTxn(m, "outflow", stock, "supplier"))
            txns.append(CashflowTxn(m, "outflow", 200_000, "rent"))

        offer = LoanOffer(
            principal_minor=1_500_000,
            monthly_interest_rate=0.025,
            upfront_fee_minor=30_000,
            term_months=6,
        )
        dec = underwrite_cashflow("SME-KLA-104", txns, offer)
        print(
            json.dumps(
                {
                    "applicant_id": dec.applicant_id,
                    "decision": dec.decision,
                    "risk_grade": dec.risk_grade,
                    "dscr_median": dec.dscr_median,
                    "dscr_stress": dec.dscr_stress,
                    "max_safe_principal_ugx": dec.max_safe_principal_minor,
                    "effective_apr_pct": dec.disclosure.effective_apr_pct,
                    "monthly_installment_ugx": dec.disclosure.monthly_installment_minor,
                    "reason_codes": list(dec.reason_codes),
                },
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
