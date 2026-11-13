"""
On-demand, single-category retail invoice fetch - the retail equivalent of
fetch_latest_invoice (rental), scoped to one API-Gateway-callable Lambda invocation that
reliably finishes well inside API Gateway's fixed 30s integration timeout.

Only sweeps the last ON_DEMAND_SWEEP_WINDOW_HOURS hours (default 12, matching
fetch_and_classify_retail_invoices' own cron cadence - anything older than that would
already have been picked up by the last cron run) and only classifies against one
caller-specified category, to keep the per-call Jev/Gemini workload small and bounded.

Gmail's after:/before: query operators are day-granularity only, so the Gmail query
itself requests a 1-day window (yesterday through today); the real hour-granularity
cutoff is enforced per-candidate via min_internal_date_ms (see utils.retail_sweep).

Also sweeps the caller's Outlook inbox over the same window when one is linked. Outlook is
best-effort: it runs after Gmail under a tight Graph budget and a deadline derived from the
Lambda's remaining time, and its failure never fails the request - per-provider status is
returned under 'providers'.

Response reports the count of candidates classified and uploaded to S3 for extraction
(outcome_counts['uploaded_for_extraction']), not a confirmed "written to RetailInvoices"
count - parse_retail_invoice runs asynchronously off the S3 upload event and isn't
synchronously callable from here. The app should treat this as "N new invoices found,
they'll appear soon" rather than an immediate, guaranteed-visible count.
"""

import os
import json
import boto3
import time
import logging
from datetime import date, datetime, timedelta, timezone

from utils.decorators import require_auth
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.dynamodb_utils import fetch_user_by_id
from utils.exceptions import (
    GmailAPIError, OAuthValidationError, SecretsManagerError, RefreshTokenExpiredError,
    UserNotFoundError, DatabaseError
)
from utils.retail_sweep import process_user_sweep, SUPPORTED_CATEGORIES
from utils.outlook_retail_sweep import process_user_sweep as process_outlook_user_sweep
from utils.secretsmanager_utils import get_outlook_oauth_tokens

dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_WINDOW_HOURS = 12
MAX_PAGES = 1  # Up to 500 candidate messages - plenty for a single category over 12h.

# Outlook runs after Gmail inside the same 28s Lambda budget: one page (50 messages), a
# short single-attempt Graph list call, and stop classifying with this much time left.
OUTLOOK_MAX_PAGES = 1
OUTLOOK_GRAPH_TIMEOUT_SECONDS = 8
OUTLOOK_GRAPH_MAX_ATTEMPTS = 1
OUTLOOK_DEADLINE_SAFETY_MS = 4000


def sweep_outlook_if_linked(user: dict, category: str, since: datetime, context) -> dict:
    """Best-effort on-demand Outlook sweep; returns a per-provider status dict and never raises."""
    user_id = user['UserID']
    try:
        get_outlook_oauth_tokens(user_id, region=os.environ['REGION'])
    except SecretsManagerError:
        return {'status': 'not_linked', 'newInvoicesFound': 0, 'candidatesScanned': 0}

    stop_at = None
    if context is not None and hasattr(context, 'get_remaining_time_in_millis'):
        budget_ms = context.get_remaining_time_in_millis() - OUTLOOK_DEADLINE_SAFETY_MS
        stop_at = time.monotonic() + max(budget_ms, 0) / 1000

    try:
        result = process_outlook_user_sweep(
            user, max_pages=OUTLOOK_MAX_PAGES, category_filter=category, since=since,
            graph_timeout=OUTLOOK_GRAPH_TIMEOUT_SECONDS, graph_max_attempts=OUTLOOK_GRAPH_MAX_ATTEMPTS,
            stop_at_monotonic=stop_at
        )
    except RefreshTokenExpiredError as e:
        logger.warning(f"On-demand Outlook sweep for user {user_id}: token expired - {e}")
        return {'status': 'reconnect_required', 'newInvoicesFound': 0, 'candidatesScanned': 0}
    except Exception as e:
        logger.error(f"On-demand Outlook sweep failed for user {user_id}: {e}")
        return {'status': 'error', 'newInvoicesFound': 0, 'candidatesScanned': 0}

    return {
        'status': 'ok',
        'newInvoicesFound': result['outcome_counts'].get('uploaded_for_extraction', 0),
        'candidatesScanned': result['candidates_found'],
        'deferred': result['outcome_counts'].get('deferred_time_budget', 0),
    }


@require_auth
def lambda_handler(event, context, user_id):
    """Fetch the latest retail invoices for one category, for the authenticated caller."""
    try:
        body = {}
        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']

        category = body.get('category')
        if category not in SUPPORTED_CATEGORIES:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                f"Invalid or missing 'category'. Must be one of: {SUPPORTED_CATEGORIES}",
                400, ValueError("Invalid category")
            )

        users_table = dynamodb.Table(os.environ['USERS_TABLE'])
        user = fetch_user_by_id(users_table, user_id)

        window_hours = int(os.environ.get('ON_DEMAND_SWEEP_WINDOW_HOURS', str(DEFAULT_WINDOW_HOURS)))
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        cutoff_ms = int(since.timestamp() * 1000)

        # Gmail query window is day-granularity only - the real cutoff is min_internal_date_ms.
        start_date = (date.today() - timedelta(days=1)).isoformat()
        end_date = date.today().isoformat()

        result = process_user_sweep(
            user, backfill_start_date=start_date, backfill_end_date=end_date,
            max_pages=MAX_PAGES, category_filter=category, min_internal_date_ms=cutoff_ms
        )

        gmail_new = result['outcome_counts'].get('uploaded_for_extraction', 0)
        outlook = sweep_outlook_if_linked(user, category, since, context)

        new_count = gmail_new + outlook['newInvoicesFound']
        scanned = result['candidates_found'] + outlook['candidatesScanned']
        logger.info(f"On-demand fetch for user {user_id}, category '{category}': "
                    f"{new_count} new invoices found ({scanned} candidates scanned; "
                    f"gmail={gmail_new}/{result['candidates_found']}, outlook={outlook})")

        return success_response(
            message=f"Retail invoice fetch complete for category '{category}'",
            data={
                'newInvoicesFound': new_count,
                'category': category,
                'candidatesScanned': scanned,
                'dateRange': result['date_range'],
                'providers': {
                    'gmail': {'status': 'ok', 'newInvoicesFound': gmail_new,
                              'candidatesScanned': result['candidates_found']},
                    'outlook': outlook,
                },
            }
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except GmailAPIError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Gmail API error", 502, e)

    except RefreshTokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.GMAIL_TOKEN_EXPIRED, "Gmail account needs to be re-connected", 502, e)

    except OAuthValidationError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "OAuth token error", 401, e)

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.GMAIL_TOKEN_EXPIRED, "Error retrieving OAuth tokens", 502, e)

    except UserNotFoundError as e:
        return log_and_generate_error_response(ErrorCode.USER_NOT_FOUND, "User not found", 404, e)

    except DatabaseError as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Database error", 500, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
