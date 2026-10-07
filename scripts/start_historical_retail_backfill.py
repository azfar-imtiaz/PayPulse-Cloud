#!/usr/bin/env python3
"""
Kicks off a historical retail invoice backfill by starting one execution of the
retail-invoice-backfill Step Functions state machine.

Computes a list of non-overlapping, chunk-months-sized batch windows from --start-year
to today, and passes them as the execution's input. The state machine itself is
generic/dumb - it just fans the batch list out to fetch_and_classify_retail_invoices
with bounded concurrency and built-in retry; no orchestration logic lives in this
script beyond the date math.

No polling/threading/retry logic here - once the execution starts, check progress via:
    aws stepfunctions describe-execution --execution-arn <arn>
    aws stepfunctions get-execution-history --execution-arn <arn>
or the AWS Console's execution graph.

Usage:
    python3 scripts/start_historical_retail_backfill.py --user-id user_abc123
    python3 scripts/start_historical_retail_backfill.py --user-id user_abc123 --start-year 2020 --chunk-months 3 --max-pages 15
"""

import argparse
import json
import sys
from datetime import date

import boto3

# Must match MAX_BACKFILL_WINDOW_DAYS in
# lambdas/invoices/fetch_and_classify_retail_invoices/lambda_function.py - kept as a
# separate constant here (not imported) since this script runs locally, outside the
# Lambda's deployment package.
MAX_BACKFILL_WINDOW_DAYS = 186

STATE_MACHINE_NAME = "retail-invoice-backfill"
REGION = "eu-west-1"


def add_months(d: date, months: int) -> date:
    """Add a number of months to a date, clamping the day if the target month is shorter."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def build_batches(start_year: int, chunk_months: int, max_pages: int) -> list:
    """Generate non-overlapping [start_date, end_date) windows from Jan 1 of start_year to today."""
    batches = []
    window_start = date(start_year, 1, 1)
    today = date.today()

    while window_start < today:
        window_end = min(add_months(window_start, chunk_months), today)
        batches.append({
            "start_date": window_start.isoformat(),
            "end_date": window_end.isoformat(),
            "max_pages": max_pages,
        })
        window_start = window_end

    return batches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="User ID to backfill retail invoices for")
    parser.add_argument("--start-year", type=int, default=2020, help="Earliest year to backfill from (default: 2020)")
    parser.add_argument("--chunk-months", type=int, default=3, help="Batch window size in months (default: 3, hard max: 6)")
    parser.add_argument("--max-pages", type=int, default=15, help="Gmail pagination cap per batch (default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Print the computed batches without starting an execution")
    args = parser.parse_args()

    if args.chunk_months * 31 > MAX_BACKFILL_WINDOW_DAYS:
        print(f"Error: --chunk-months {args.chunk_months} risks exceeding the Lambda's "
              f"{MAX_BACKFILL_WINDOW_DAYS}-day hard cap. Use 6 or fewer.", file=sys.stderr)
        sys.exit(1)

    batches = build_batches(args.start_year, args.chunk_months, args.max_pages)
    print(f"Computed {len(batches)} batches from {args.start_year}-01-01 to {date.today().isoformat()}:")
    for b in batches:
        print(f"  {b['start_date']} -> {b['end_date']}")

    if args.dry_run:
        print("\nDry run - no execution started.")
        return

    sfn = boto3.client("stepfunctions", region_name=REGION)
    state_machines = sfn.list_state_machines()["stateMachines"]
    state_machine_arn = next(
        (sm["stateMachineArn"] for sm in state_machines if sm["name"] == STATE_MACHINE_NAME), None
    )
    if not state_machine_arn:
        print(f"Error: state machine '{STATE_MACHINE_NAME}' not found in region {REGION}.", file=sys.stderr)
        sys.exit(1)

    execution_input = {"user_id": args.user_id, "batches": batches}
    response = sfn.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(execution_input),
    )

    print(f"\nStarted execution: {response['executionArn']}")
    print("Check progress with:")
    print(f"  aws stepfunctions describe-execution --execution-arn {response['executionArn']}")
    print(f"  aws stepfunctions get-execution-history --execution-arn {response['executionArn']}")


if __name__ == "__main__":
    main()
