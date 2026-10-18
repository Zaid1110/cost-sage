# cost-sage — AWS Cost Advisor

## What this is

cost-sage reads an AWS Cost Explorer-style CSV export and flags common cloud
waste using simple, documented heuristics: idle EC2/RDS instances, oversized
EC2 instances, unattached EBS volumes and old EBS snapshots. It prints a
savings report with estimated monthly savings in USD and INR.

Fully offline for the demo — no AWS credentials, no network, no cost to run.
The spot where a live Cost Explorer API integration would plug in is marked
with a `TODO` in `fetch_live_costs()` inside `cost_sage.py`.

## What problem it solves

Cloud bills grow quietly. Idle instances left running after a project ends,
EBS volumes orphaned when their instance is terminated, and snapshots nobody
deleted keep billing every month. Most teams discover this waste only when
finance asks why the bill doubled — usually months of spend later.

## Benefits

- **Finds real money fast:** one command surfaces the top waste items with
  dollar and rupee estimates, ranked by saving.
- **Safe signals, not orders:** every finding carries a confidence level and
  the exact heuristic used, so an engineer can review before touching
  anything.
- **Zero-risk evaluation:** the bundled synthetic CSV demonstrates the full
  report with no AWS account needed.
- **Transparent math:** thresholds (5% CPU = idle, 20% = oversized, 90 days =
  old snapshot) are printed in the report and easy to tune for your org.

## Before vs After

| Before | After |
|---|---|
| Cloud bill reviewed quarterly in a spreadsheet; idle resources billed for months | `python3 cost_sage.py report export.csv` → waste list in seconds |
| "Are we overspending?" answered with gut feeling | Answered with a ranked savings report: $262.50/mo on the sample data |
| Cleanup = ad-hoc clicking through the console | Findings map 1:1 to resources (instance/volume/snapshot IDs) for scripting |

## How to run the demo

```bash
chmod +x demo.sh
./demo.sh
```

Expected output: 11 resources scanned, 6 findings, ~$262.50/mo potential
savings (Rs ~21,788 at the default 83 INR/USD rate). All sample data is
synthetic.

Use your own export:

```bash
python3 cost_sage.py report my-cost-export.csv --rate 84.5
```

### How to export the real CSV from the AWS console

1. Open **AWS Billing Console → Cost Explorer**.
2. Set the date range (e.g. last full month), Group by **Resource** or
   **Service**, and add a filter if you want one account/region.
3. Click **Download CSV** (top-right of the table).
4. The CSV must have these columns (rename/reorder as needed):

   `resource_id, service, resource_type, region, state, avg_cpu_pct,`
   `age_days, attached_to, instance_type, size_gb, monthly_cost_usd, notes`

   - `resource_type`: `instance`, `volume`, `snapshot`, `db-instance`
   - `state`: for EC2 use `running`/`stopped`; for EBS volumes use
     `in-use`/`available`; snapshots use `completed`
   - `avg_cpu_pct`: average CPU utilisation over the period (from CloudWatch)
   - `age_days`: for snapshots, age of the snapshot

## Architecture (short)

```
cost_export.csv
   │  csv.DictReader
   ▼
find_waste()  ── heuristic rule table per resource_type
   │    idle EC2/RDS: running + cpu < 5%      → full cost
   │    oversized EC2: cpu < 20%              → 50% of cost
   │    unattached EBS: state == 'available'  → full cost
   │    old snapshot: age > 90 days           → full cost
   ▼
print_report() ── ranked findings + USD/INR totals
```

## Roadmap

- Live mode: pull real data via the Cost Explorer + CloudWatch APIs
  (`fetch_live_costs()` is the integration point).
- More checks: unassociated Elastic IPs, old AMIs, S3 buckets without
  lifecycle policies, idle load balancers.
- `--fix --dry-run` mode that prints the exact AWS CLI commands to clean up.
- Weekly scheduled report (cron) with Slack/email summary.

## Notes

- The sample CSV in `sample_data/` is synthetic — resource IDs are invented.
- Savings are estimates from documented heuristics, not AWS billing figures.
  Always verify in the console before deleting anything.
