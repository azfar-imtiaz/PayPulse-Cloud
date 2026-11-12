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

Response reports the count of candidates classified and uploaded to S3 for extraction
(outcome_counts['uploaded_for_extraction']), not a confirmed "written to RetailInvoices"
count - parse_retail_invoice runs asynchronously off the S3 upload event and isn't
synchronously callable from here. The app should treat this as "N new invoices found,
they'll appear soon" rather than an immediate, guaranteed-visible count.
"""

import os
import json
import boto3
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

dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_WINDOW_HOURS = 12
MAX_PAGES = 1  # Up to 500 candidate messages - plenty for a single category over 12h.


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
        cutoff_ms = int((datetime.now(timezone.utc) - timedelta(hours=window_hours)).timestamp() * 1000)

        # Gmail query window is day-granularity only - the real cutoff is min_internal_date_ms.
        start_date = (date.today() - timedelta(days=1)).isoformat()
        end_date = date.today().isoformat()

        result = process_user_sweep(
            user, backfill_start_date=start_date, backfill_end_date=end_date,
            max_pages=MAX_PAGES, category_filter=category, min_internal_date_ms=cutoff_ms
        )

        new_count = result['outcome_counts'].get('uploaded_for_extraction', 0)
        logger.info(f"On-demand fetch for user {user_id}, category '{category}': "
                    f"{new_count} new invoices found ({result['candidates_found']} candidates scanned)")

        return success_response(
            message=f"Retail invoice fetch complete for category '{category}'",
            data={
                'newInvoicesFound': new_count,
                'category': category,
                'candidatesScanned': result['candidates_found'],
                'dateRange': result['date_range'],
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
