"""
API-triggered entry point for the historical retail invoice backfill.

NOTE: this endpoint is untested (no real invocation via API Gateway has been made).
It was implemented for completeness - mirroring scripts/start_historical_retail_backfill.py
so the same backfill capability is reachable from the app, not just the CLI - but has not
been exercised end-to-end. Verify with a real authenticated request before relying on it.

Derives user_id from the caller's JWT (not request body), so a user can only ever trigger
a backfill for their own account. Computes the same bounded, non-overlapping batch windows
the CLI script does, then starts one execution of the retail-invoice-backfill Step
Functions state machine - no polling/orchestration here, same as the CLI's approach.

TODO: this endpoint is fire-and-forget - start_execution returns immediately with an
executionArn, and the backfill then runs independently with no way for the caller to
learn when it finishes. Two options, neither built yet:
  1. Polling endpoint - GET /v1/invoices/retail/backfill/status?executionArn=...,
     authenticated the same way, wraps states:DescribeExecution and returns
     {status, startDate, stopDate}. Smallest addition; app just polls after kicking off
     a backfill.
  2. Push notification on completion - an EventBridge rule on Step Functions execution
     state-change events for this state machine, feeding the existing
     NewInvoiceNotificationTopic SNS topic (already used for new-invoice push
     notifications). Needs a way to map the completed execution back to the triggering
     user (e.g. parse user_id out of the execution's stored input in the event detail)
     before notifying that user's device.
Deferred until the app-facing feature is actually prioritized.
"""

import os
import json
import boto3
import logging
from datetime import date

from utils.decorators import require_auth
from utils.responses import success_response, log_and_generate_error_response, ErrorCode

sfn_client = boto3.client('stepfunctions')

logging.basicConfig(level=logging.INFO)

STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']

# Must match MAX_BACKFILL_WINDOW_DAYS in
# lambdas/invoices/fetch_and_classify_retail_invoices/lambda_function.py and the
# equivalent constant in scripts/start_historical_retail_backfill.py - kept as a separate
# constant here since this Lambda doesn't share a deployment package with that one.
MAX_BACKFILL_WINDOW_DAYS = 186

DEFAULT_START_YEAR = 2020
DEFAULT_CHUNK_MONTHS = 3
DEFAULT_MAX_PAGES = 15


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


@require_auth
def lambda_handler(event, context, user_id):
    """Start a historical retail invoice backfill for the authenticated caller."""
    try:
        body = {}
        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']

        start_year = body.get('start_year', DEFAULT_START_YEAR)
        chunk_months = body.get('chunk_months', DEFAULT_CHUNK_MONTHS)
        max_pages = body.get('max_pages', DEFAULT_MAX_PAGES)

        if chunk_months * 31 > MAX_BACKFILL_WINDOW_DAYS:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                f"chunk_months {chunk_months} risks exceeding the backfill Lambda's "
                f"{MAX_BACKFILL_WINDOW_DAYS}-day hard cap per batch. Use 6 or fewer.",
                400, ValueError("chunk_months too large")
            )

        batches = build_batches(start_year, chunk_months, max_pages)
        logging.info(f"Starting backfill for user {user_id}: {len(batches)} batches from {start_year}-01-01")

        execution_input = {"user_id": user_id, "batches": batches}
        response = sfn_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(execution_input),
        )

        return success_response(
            message="Historical retail invoice backfill started",
            data={
                'executionArn': response['executionArn'],
                'batchCount': len(batches),
                'startYear': start_year,
                'chunkMonths': chunk_months,
            }
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
