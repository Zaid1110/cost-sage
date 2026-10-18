#!/usr/bin/env python3
"""
cost-sage: AWS Cost Advisor.

Reads an AWS Cost Explorer-style CSV export and flags common waste using
simple, documented heuristics:

  * idle EC2 instances      - running, avg CPU < 5%   -> full monthly cost wasted
  * oversized EC2 instances - running, avg CPU < 20%  -> ~50% of cost could be saved by rightsizing
  * unattached EBS volumes  - state "available"       -> full monthly cost wasted
  * old EBS snapshots       - age > 90 days           -> full monthly cost wasted
  * idle RDS instances      - avg CPU < 5%            -> full monthly cost wasted

Fully offline for the demo - no AWS credentials needed. See README for how
to export the real CSV from the AWS console, and where a live Cost Explorer
API integration would plug in (TODO marker in fetch_live_costs()).

Usage:
    python3 cost_sage.py report sample_data/cost_export.csv
    python3 cost_sage.py report my-export.csv --rate 84.5   # custom USD->INR rate
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

USD_INR_RATE = float(os.environ.get("USD_INR_RATE", "83.0"))

IDLE_CPU_PCT = 5.0
OVERSIZED_CPU_PCT = 20.0
OLD_SNAPSHOT_DAYS = 90


def load_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def find_waste(rows: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for row in rows:
        rid = row.get("resource_id", "").strip()
        service = row.get("service", "").strip()
        rtype = row.get("resource_type", "").strip()
        state = (row.get("state", "") or "").strip().lower()
        cpu = _f(row.get("avg_cpu_pct", ""))
        age = _i(row.get("age_days", ""))
        cost = _f(row.get("monthly_cost_usd", ""))
        notes = (row.get("notes", "") or "").strip()

        if rtype == "instance" and service == "EC2" and state == "running":
            if cpu < IDLE_CPU_PCT and cost > 0:
                findings.append(
                    {
                        "resource": rid,
                        "issue": "Idle EC2 instance",
                        "detail": f"Running but only {cpu:.1f}% avg CPU (< {IDLE_CPU_PCT}%). "
                        "Stop it or terminate if it is no longer needed.",
                        "monthly_saving_usd": round(cost, 2),
                        "confidence": "high",
                    }
                )
            elif cpu < OVERSIZED_CPU_PCT and cost > 0:
                findings.append(
                    {
                        "resource": rid,
                        "issue": "Oversized EC2 instance",
                        "detail": f"Only {cpu:.1f}% avg CPU (< {OVERSIZED_CPU_PCT}%). "
                        f"Consider downsizing {row.get('instance_type', '').strip()} "
                        "one size; estimated ~50% saving.",
                        "monthly_saving_usd": round(cost * 0.5, 2),
                        "confidence": "medium",
                    }
                )
        elif rtype == "volume" and state == "available" and cost > 0:
            findings.append(
                {
                    "resource": rid,
                    "issue": "Unattached EBS volume",
                    "detail": f"Volume is not attached to any instance "
                    f"({row.get('attached_to', '').strip() or 'no attachment'}). "
                    "Snapshot and delete if the data is not needed.",
                    "monthly_saving_usd": round(cost, 2),
                    "confidence": "high",
                }
            )
        elif rtype == "snapshot" and age > OLD_SNAPSHOT_DAYS and cost > 0:
            findings.append(
                {
                    "resource": rid,
                    "issue": "Old EBS snapshot",
                    "detail": f"Snapshot is {age} days old (> {OLD_SNAPSHOT_DAYS}). "
                    "Verify retention policy, then delete if superseded.",
                    "monthly_saving_usd": round(cost, 2),
                    "confidence": "medium",
                }
            )
        elif rtype == "db-instance" and cpu < IDLE_CPU_PCT and cost > 0:
            findings.append(
                {
                    "resource": rid,
                    "issue": "Idle RDS instance",
                    "detail": f"Only {cpu:.1f}% avg CPU (< {IDLE_CPU_PCT}%). "
                    "Consider stopping it when unused or downsizing the instance class.",
                    "monthly_saving_usd": round(cost, 2),
                    "confidence": "medium",
                }
            )
    return findings


def fetch_live_costs():
    """TODO: plug in the live AWS Cost Explorer API here.

    Example shape (boto3):
        import boto3
        ce = boto3.client("ce")
        ce.get_cost_and_usage(TimePeriod={...}, Granularity="MONTHLY",
                              Metrics=["BlendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": "RESOURCE_ID"}])
    The demo below works fully offline on the CSV sample.
    """
    raise NotImplementedError("Live Cost Explorer integration is a roadmap item.")


def print_report(rows: list[dict], findings: list[dict], rate: float) -> None:
    total_spend = sum(_f(r.get("monthly_cost_usd", "")) for r in rows)
    total_saving = sum(f["monthly_saving_usd"] for f in findings)

    print("# cost-sage savings report\n")
    print(f"Resources scanned : {len(rows)}")
    print(f"Findings          : {len(findings)}")
    print(f"Total monthly spend: ${total_spend:,.2f} (Rs {total_spend * rate:,.0f})")
    print(f"Potential savings  : ${total_saving:,.2f}/mo (Rs {total_saving * rate:,.0f}/mo)")
    print()
    if not findings:
        print("No waste detected with the current heuristics. Nice work.")
        return

    print(f"{'RESOURCE':<28} {'ISSUE':<24} {'SAVING/MO':>12}  DETAIL")
    print("-" * 110)
    for f in sorted(findings, key=lambda x: -x["monthly_saving_usd"]):
        saving = f"${f['monthly_saving_usd']:,.2f}"
        print(f"{f['resource']:<28} {f['issue']:<24} {saving:>12}  {f['detail']}")
    print()
    print("Heuristics used: idle = running + avg CPU < 5% | oversized = avg CPU < 20% "
          "(~50% saving assumed on downsize) | unattached EBS = state 'available' | "
          "old snapshot = age > 90 days. Review each finding before acting - "
          "these are signals, not orders.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AWS cost waste finder.")
    parser.add_argument("command", choices=["report"], help="Action to run.")
    parser.add_argument("csvfile", help="Cost Explorer CSV export to analyse.")
    parser.add_argument(
        "--rate",
        type=float,
        default=USD_INR_RATE,
        help=f"USD->INR conversion rate (default: env USD_INR_RATE or {USD_INR_RATE}).",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.csvfile):
        print(f"CSV file not found: {args.csvfile}", file=sys.stderr)
        return 1

    rows = load_rows(args.csvfile)
    findings = find_waste(rows)
    print_report(rows, findings, args.rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
