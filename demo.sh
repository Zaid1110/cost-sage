#!/usr/bin/env bash
# Demo: run cost-sage on the sample Cost Explorer CSV. Fully offline.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== cost-sage demo (offline, synthetic sample data) ==="
echo
python3 cost_sage.py report sample_data/cost_export.csv
