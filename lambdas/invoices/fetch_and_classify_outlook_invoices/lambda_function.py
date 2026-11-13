"""
Broad Outlook/Microsoft Graph sweep + Jev classification Lambda for automated retail
invoice discovery - cron/backfill entry point only.

Second email provider feeding the same pipeline fetch_and_classify_retail_invoices (Gmail)
feeds. The sweep/classify/upload logic lives in utils.outlook_retail_sweep (shared common
layer module) so the on-demand endpoint (fetch_latest_retail_invoices) can reuse it.

Scope: retail invoices only. fetch_latest_invoice (rental) is untouched by this pipeline.
"""

import os
import json
import boto3
import logging
from datetime import datetime

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import get_outlook_oauth_tokens
from utils.dynamodb_utils import fetch_user_by_id
from utils.exceptions import (
    OutlookAPIError, OAuthValidationError, SecretsManagerError, RefreshTokenExpiredError,
    UserNotFoundError, DatabaseError
)
from utils.outlook_retail_sweep import process_user_sweep, MAX_BACKFILL_WINDOW_DAYS

dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def process_single_user_backfill(user_id: str, start_date: str, end_date: str, max_pages: int = None) -> dict:
    """
    Backfill entry point scoped to exactly one user - never scans Users. Mirrors Gmail's
    process_single_user_backfill.

    Returns the same result shape process_all_users_sweep does, so
    lambda_handler's success_response call doesn't need separate handling.
    """
    users_table = dynamodb.Table(os.environ['USERS_TABLE'])
    user = fetch_user_by_id(users_table, user_id)

    result = process_user_sweep(user, backfill_start_date=start_date, backfill_end_date=end_date,
                                 max_pages=max_pages)

    return {'total_users': 1, 'successful': 1, 'failed': 0, 'per_user': [result], 'errors': []}


def process_all_users_sweep(backfill_start_date: str = None, max_pages: int = None) -> dict:
    """
    EventBridge trigger path: sweep every user's Outlook inbox.

    Users without a linked Outlook account (no outlook/user/{user_id} secret) are skipped,
    not counted as failures - most users will only have Gmail linked.
    """
    users_table = dynamodb.Table(os.environ['USERS_TABLE'])
    response = users_table.scan()
    users = response['Items']

    results = {'total_users': len(users), 'successful': 0, 'failed': 0, 'skipped_no_outlook': 0,
               'per_user': [], 'errors': []}

    for user in users:
        user_id = user.get('UserID')
        try:
            get_outlook_oauth_tokens(user_id, region=os.environ['REGION'])
        except SecretsManagerError:
            results['skipped_no_outlook'] += 1
            continue

        try:
            result = process_user_sweep(user, backfill_start_date=backfill_start_date, max_pages=max_pages)
            results['per_user'].append(result)
            results['successful'] += 1
        except Exception as e:
            logger.error(f"Error sweeping Outlook for user {user_id}: {e}")
            results['failed'] += 1
            results['errors'].append({'user_id': user_id, 'error': str(e)})

    return results


def lambda_handler(event, context):
    """
    Main entry point.

    Modes:
    - Manual backfill: event = {"mode": "backfill", "user_id": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "max_pages": <int>}
      Sweeps exactly one user's Outlook inbox over a bounded window (max MAX_BACKFILL_WINDOW_DAYS).
    - EventBridge (scheduled): sweeps all Outlook-linked users using gap-filling incremental windows.

    No API Gateway route in v1 - this pipeline runs exclusively on its own cron (shared
    with the Gmail sweep's retail_sweep_trigger rule) plus manual backfill invocations.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        if event.get('mode') == 'backfill':
            logger.info("Backfill mode detected")
            user_id = event.get('user_id')
            start_date_str = event.get('start_date')
            end_date_str = event.get('end_date')

            if not user_id or not start_date_str or not end_date_str:
                return log_and_generate_error_response(
                    ErrorCode.MISSING_FIELDS,
                    "Backfill mode requires user_id, start_date, and end_date",
                    400, ValueError("Missing required backfill field")
                )

            span_days = (datetime.strptime(end_date_str, "%Y-%m-%d")
                         - datetime.strptime(start_date_str, "%Y-%m-%d")).days
            if span_days > MAX_BACKFILL_WINDOW_DAYS:
                return log_and_generate_error_response(
                    ErrorCode.INVALID_REQUEST,
                    f"Backfill window cannot exceed {MAX_BACKFILL_WINDOW_DAYS} days ({span_days} requested)",
                    400, ValueError("Backfill window too large")
                )

            results = process_single_user_backfill(
                user_id=user_id, start_date=start_date_str, end_date=end_date_str,
                max_pages=event.get('max_pages')
            )
            return success_response(message="Backfill sweep completed", data=results)

        if 'source' in event and event['source'] == 'aws.events':
            logger.info("EventBridge trigger detected - sweeping all Outlook-linked users")
            results = process_all_users_sweep()
            return success_response(message="Outlook retail invoice sweep completed", data=results)

        logger.warning("Unrecognized trigger - this Lambda has no API Gateway route")
        return log_and_generate_error_response(
            ErrorCode.INVALID_JSON, "Unrecognized trigger source", 400,
            ValueError("Expected an EventBridge event or a backfill-mode invocation")
        )

    except OutlookAPIError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Outlook API error", 502, e)

    except RefreshTokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.OUTLOOK_TOKEN_EXPIRED, "Outlook account needs to be re-connected", 502, e)

    except OAuthValidationError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "OAuth token error", 401, e)

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.OUTLOOK_TOKEN_EXPIRED, "Error retrieving OAuth tokens", 502, e)

    except UserNotFoundError as e:
        return log_and_generate_error_response(ErrorCode.USER_NOT_FOUND, "User not found", 404, e)

    except DatabaseError as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Database error", 500, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
