"""
Broad Gmail sweep + Jev classification Lambda for automated retail invoice discovery.

Replaces vendor-scoped discovery (fetch_retail_invoices) with a date-bounded sweep of the
whole inbox, classified via a single combined Jev (TypeSafe AI) call per candidate email.
Every classification outcome is recorded in RetailEmailClassificationLedger regardless of
result. Confirmed candidates are uploaded to S3 (same key scheme as today, tagged with
sweep-origin metadata) which re-triggers the existing, unchanged parse_retail_invoice
Lambda to run Gemini extraction and the DB write.

Scope: retail invoices only. fetch_latest_invoice (rental) is untouched by this pipeline.
"""

import os
import json
import boto3
import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import get_oauth_tokens
from utils.dynamodb_utils import (
    fetch_user_by_id, update_last_retail_sweep_fetch, write_ledger_entry, get_ledger_entry
)
from utils.gmail_api_utils import (
    create_gmail_service, build_sweep_gmail_query, get_email_metadata_light,
    derive_vendor_slug_from_sender, get_email_content, extract_html_from_email
)
from utils.s3_utils import generate_retail_invoice_s3_key, upload_html_to_s3
from utils.exceptions import (
    GmailAPIError, OAuthValidationError, SecretsManagerError, RefreshTokenExpiredError,
    UserNotFoundError, DatabaseError, ClassificationError
)

from jev_client import classify_email
from gemini_fallback import gemini_category_fallback

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Categories with an implemented Gemini parser in lambda_layers/gemini_parsers/parser_factory.py.
# Keep in sync with that file's parser_mapping - any category not listed here parks as
# `parked_unsupported_category` instead of being uploaded for extraction.
SUPPORTED_CATEGORIES = [
    'food-delivery',
    'miscellaneous',
    'technology',
    'clothing',
    'travel',
    'subscriptions',
    'grocery',
    'utility',
]

# Short disambiguation hints fed into Jev's Choice criteria (and the Gemini fallback
# prompt) so classification has real guidance instead of bare labels. Added after
# reviewing the first production run: parking providers were landing in 'miscellaneous'
# instead of 'travel', and cloud/SaaS billing (AWS, GCP) was landing in 'technology'
# instead of 'subscriptions'. Tune these as more misclassification patterns surface.
CATEGORY_DESCRIPTIONS = {
    'food-delivery': (
        "Restaurant or food delivery orders - meals ordered for delivery or pickup "
        "(e.g. Foodora, Uber Eats, Dominos)."
    ),
    'clothing': "Clothing, shoes, or apparel purchases.",
    'technology': (
        "One-time purchases of technology hardware, gadgets, or software/app licenses. "
        "Does NOT include recurring cloud or SaaS platform bills - those belong in "
        "'subscriptions' even though the vendor sounds technical (e.g. an AWS or Google "
        "Cloud invoice is a subscription, not technology)."
    ),
    'subscriptions': (
        "Recurring, regularly-billed services: streaming, cloud/SaaS platforms (AWS, "
        "Google Cloud, Azure, Anthropic, OpenAI), software subscriptions, and recurring "
        "membership or community dues (gym, club, religious organization). If the email "
        "describes a monthly or periodic charge, prefer this category even if the vendor "
        "sounds technical or otherwise unrelated."
    ),
    'grocery': "Grocery store or supermarket purchases.",
    'utility': "Home utility bills: electricity, water, heating, or home internet/broadband service.",
    'miscellaneous': (
        "General purchases that don't clearly fit any other category. Use this only "
        "when no other category applies."
    ),
    'travel': (
        "Transportation and travel-related purchases: flights, trains, ride-hailing, "
        "parking, tolls, hotels. Parking providers (e.g. Parkering, EasyPark, APCOA, "
        "P-Hus, Parkster) always belong here, not 'miscellaneous'."
    ),
}

DEFAULT_SWEEP_DAYS = 30

# Hard cap on a single backfill batch's window, enforced before any Gmail/Jev/Gemini
# work happens. Historical ranges (e.g. 2020-now) must be split into multiple batches by
# the caller (see the retail-invoice-backfill Step Functions state machine) - this Lambda
# deliberately refuses to do that splitting itself, to keep each invocation's wall-clock
# time well under the 900s Lambda timeout.
MAX_BACKFILL_WINDOW_DAYS = 186


def determine_sweep_date_range(user: dict, default_days: int = DEFAULT_SWEEP_DAYS,
                                backfill_start_date: str = None, backfill_end_date: str = None) -> tuple:
    """
    Determine the sweep's date window using gap-filling semantics: a missed run must not
    create a silent coverage hole, so the window always covers the full elapsed gap since
    the last successful run, not a fixed "last N days".

    Args:
        user: User dict from DynamoDB
        default_days: Fallback window size (days) when no prior sweep timestamp exists
        backfill_start_date: Optional override "YYYY-MM-DD" for manual backfill mode
        backfill_end_date: Optional override "YYYY-MM-DD" bounding the end of a backfill
            window - only meaningful when backfill_start_date is also set. Without this,
            backfill mode would always sweep to "now", making bounded historical batches
            (e.g. one quarter of 2020) impossible.

    Returns:
        Tuple of (start_date, end_date) in Gmail format "YYYY/MM/DD"
    """
    end_date = datetime.now(timezone.utc).strftime("%Y/%m/%d")

    if backfill_start_date:
        start_dt = datetime.strptime(backfill_start_date, "%Y-%m-%d")
        start_date = start_dt.strftime("%Y/%m/%d")
        if backfill_end_date:
            end_date = datetime.strptime(backfill_end_date, "%Y-%m-%d").strftime("%Y/%m/%d")
        logger.info(f"Backfill mode: sweeping from {start_date} to {end_date}")
        return start_date, end_date

    last_sweep = user.get('last_retail_sweep_fetch')

    if last_sweep:
        try:
            last_sweep_dt = datetime.fromisoformat(last_sweep.replace('Z', '+00:00'))
            start_date = last_sweep_dt.strftime("%Y/%m/%d")
            logger.info(f"Gap-filling sweep from {start_date} to {end_date} (last sweep: {last_sweep})")
        except ValueError as e:
            logger.warning(f"Invalid last_retail_sweep_fetch timestamp: {last_sweep}. Using default window. Error: {e}")
            start_date = (datetime.now(timezone.utc) - timedelta(days=default_days)).strftime("%Y/%m/%d")
    else:
        start_date = (datetime.now(timezone.utc) - timedelta(days=default_days)).strftime("%Y/%m/%d")
        logger.info(f"First-time sweep (last {default_days} days): {start_date} to {end_date}")

    return start_date, end_date


def list_sweep_candidates(gmail_service, start_date: str, end_date: str, max_pages: int,
                           excluded_senders: list = None) -> tuple:
    """
    Paginated Gmail messages.list over the sweep window.

    Returns:
        Tuple of (message_ids: list, exhausted: bool) - exhausted is False if the page cap
        was hit before Gmail ran out of pages, signaling the caller should NOT advance
        last_retail_sweep_fetch (the next run retries this same window).
    """
    query = build_sweep_gmail_query(start_date, end_date, excluded_senders=excluded_senders)
    message_ids = []
    page_token = None
    pages_fetched = 0

    while True:
        request_kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            request_kwargs['pageToken'] = page_token

        response = gmail_service.users().messages().list(**request_kwargs).execute()
        message_ids.extend(m['id'] for m in response.get('messages', []))
        pages_fetched += 1

        page_token = response.get('nextPageToken')
        if not page_token:
            return message_ids, True

        if pages_fetched >= max_pages:
            logger.warning(f"Hit MAX_SWEEP_PAGES={max_pages} cap with more pages remaining - "
                            f"will not advance last_retail_sweep_fetch this run")
            return message_ids, False


def process_candidate_email(gmail_service, ledger_table, s3_bucket, user_id: str, message_id: str,
                             jev_api_key: str, gemini_api_key: str,
                             noul_threshold: float, choice_confidence_threshold: float) -> str:
    """
    Classify a single candidate email and, if confirmed, upload it to S3 to trigger
    extraction. Writes a ledger row for every outcome. Returns the final/interim status
    string for logging/counting purposes.
    """
    existing = get_ledger_entry(ledger_table, user_id, message_id)
    if existing:
        return 'skipped_already_classified'

    write_ledger_entry(ledger_table, user_id, message_id, status='pending')

    metadata = get_email_metadata_light(gmail_service, message_id)
    subject, sender, snippet = metadata['subject'], metadata['sender'], metadata['snippet']

    try:
        result = classify_email(jev_api_key, subject, sender, snippet, CATEGORY_DESCRIPTIONS)
    except ClassificationError as e:
        logger.error(f"Classification failed for message {message_id}: {e}")
        write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed',
                            error_detail=str(e))
        return 'classification_failed'

    noul_result = result['noul_result']
    choice_category = result['choice_category']
    choice_confidence = result['choice_confidence']
    token_usage = result['token_usage']
    used_gemini_fallback = False

    if noul_result < noul_threshold:
        write_ledger_entry(ledger_table, user_id, message_id, status='rejected_tier1',
                            noul_result=noul_result, choice_category=choice_category,
                            choice_confidence=choice_confidence, used_gemini_fallback=False,
                            jev_token_usage=token_usage)
        return 'rejected_tier1'

    if choice_category is None or choice_confidence < choice_confidence_threshold:
        used_gemini_fallback = True
        choice_category = gemini_category_fallback(gemini_api_key, subject, sender, snippet, CATEGORY_DESCRIPTIONS)

        if choice_category is None:
            write_ledger_entry(ledger_table, user_id, message_id, status='parked_unclassifiable',
                                noul_result=noul_result, choice_confidence=choice_confidence,
                                used_gemini_fallback=True, jev_token_usage=token_usage)
            return 'parked_unclassifiable'

    if choice_category not in SUPPORTED_CATEGORIES:
        write_ledger_entry(ledger_table, user_id, message_id, status='parked_unsupported_category',
                            noul_result=noul_result, choice_category=choice_category,
                            choice_confidence=choice_confidence, used_gemini_fallback=used_gemini_fallback,
                            jev_token_usage=token_usage)
        return 'parked_unsupported_category'

    # Confirmed candidate - fetch full content and hand off to the existing extraction Lambda
    email_content = get_email_content(gmail_service, message_id)
    html_content = extract_html_from_email(email_content)

    if not html_content:
        write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed',
                            choice_category=choice_category, choice_confidence=choice_confidence,
                            used_gemini_fallback=used_gemini_fallback, jev_token_usage=token_usage,
                            error_detail="No HTML content found in email")
        return 'no_html_content'

    email_date_str = email_content.get('Date')
    email_date = parsedate_to_datetime(email_date_str) if email_date_str else datetime.now(timezone.utc)

    vendor_slug = derive_vendor_slug_from_sender(sender)
    s3_key = generate_retail_invoice_s3_key(
        user_id=user_id, vendor_id=vendor_slug, sub_type=choice_category,
        email_date=email_date, message_id=message_id
    )

    upload_html_to_s3(s3_client, s3_bucket, s3_key, html_content,
                       metadata={'source': 'sweep', 'message_id': message_id})

    write_ledger_entry(ledger_table, user_id, message_id, status='pending',
                        noul_result=noul_result, choice_category=choice_category,
                        choice_confidence=choice_confidence, used_gemini_fallback=used_gemini_fallback,
                        jev_token_usage=token_usage, s3_path=s3_key)
    return 'uploaded_for_extraction'


def process_user_sweep(user: dict, backfill_start_date: str = None, backfill_end_date: str = None,
                        max_pages: int = None) -> dict:
    """
    Run the full sweep + classify flow for a single user.
    """
    user_id = user['UserID']
    users_table = dynamodb.Table(os.environ['USERS_TABLE'])
    ledger_table = dynamodb.Table(os.environ['RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE'])

    max_pages = max_pages or int(os.environ.get('MAX_SWEEP_PAGES', '10'))
    noul_threshold = float(os.environ.get('NOUL_THRESHOLD', '0.5'))
    choice_confidence_threshold = float(os.environ.get('CHOICE_CONFIDENCE_THRESHOLD', '0.6'))

    start_date, end_date = determine_sweep_date_range(user, backfill_start_date=backfill_start_date,
                                                        backfill_end_date=backfill_end_date)

    oauth_data = get_oauth_tokens(user_id, region=os.environ['REGION'])
    gmail_service = create_gmail_service(
        user_id=user_id,
        access_token=oauth_data['access_token'],
        refresh_token=oauth_data['refresh_token'],
        client_id=os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
        region=os.environ['REGION'],
        client_secret=None,
        expires_at=oauth_data.get('expires_at')
    )

    excluded_senders = [s.strip() for s in os.environ.get('EXCLUDED_SENDER_EMAILS', '').split(',') if s.strip()]
    message_ids, exhausted = list_sweep_candidates(gmail_service, start_date, end_date, max_pages,
                                                     excluded_senders=excluded_senders)
    logger.info(f"Sweep found {len(message_ids)} candidate messages for user {user_id} "
                f"({start_date} to {end_date}, exhausted={exhausted})")

    outcome_counts = {}
    for message_id in message_ids:
        try:
            outcome = process_candidate_email(
                gmail_service=gmail_service, ledger_table=ledger_table,
                s3_bucket=os.environ['S3_BUCKET'], user_id=user_id, message_id=message_id,
                jev_api_key=os.environ['JEV_API_KEY'], gemini_api_key=os.environ['GEMINI_API_KEY'],
                noul_threshold=noul_threshold, choice_confidence_threshold=choice_confidence_threshold
            )
        except Exception as e:
            logger.error(f"Error processing message {message_id} for user {user_id}: {e}")
            outcome = 'error'

        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        time.sleep(0.1)  # Rate limiting, matches fetch_retail_invoices' pattern

    if exhausted and not backfill_start_date:
        update_last_retail_sweep_fetch(users_table, user_id)

    return {
        'user_id': user_id,
        'candidates_found': len(message_ids),
        'outcome_counts': outcome_counts,
        'date_range': {'start': start_date, 'end': end_date},
        'window_exhausted': exhausted,
    }


def process_single_user_backfill(user_id: str, start_date: str, end_date: str, max_pages: int = None) -> dict:
    """
    Backfill entry point scoped to exactly one user - never scans Users. Historical
    backfill batches are invoked per-user (e.g. by the Step Functions state machine
    fanning out bounded date windows), so there's no "all users" case here the way
    there is for the EventBridge/scheduled sweep.

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
    EventBridge trigger path: sweep every user's inbox.
    """
    users_table = dynamodb.Table(os.environ['USERS_TABLE'])
    response = users_table.scan()
    users = response['Items']

    results = {'total_users': len(users), 'successful': 0, 'failed': 0, 'per_user': [], 'errors': []}

    for user in users:
        try:
            result = process_user_sweep(user, backfill_start_date=backfill_start_date, max_pages=max_pages)
            results['per_user'].append(result)
            results['successful'] += 1
        except Exception as e:
            logger.error(f"Error sweeping user {user.get('UserID')}: {e}")
            results['failed'] += 1
            results['errors'].append({'user_id': user.get('UserID'), 'error': str(e)})

    return results


def lambda_handler(event, context):
    """
    Main entry point.

    Modes:
    - Manual backfill: event = {"mode": "backfill", "user_id": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "max_pages": <int>}
      Sweeps exactly one user's inbox over a bounded window (max MAX_BACKFILL_WINDOW_DAYS).
      Intended to be invoked once per batch, e.g. by the retail-invoice-backfill Step
      Functions state machine fanning out many bounded historical windows.
    - EventBridge (scheduled): sweeps all users using gap-filling incremental windows.

    No API Gateway route in v1 - this pipeline runs exclusively on its own cron plus
    manual backfill invocations.
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
            logger.info("EventBridge trigger detected - sweeping all users")
            results = process_all_users_sweep()
            return success_response(message="Retail invoice sweep completed", data=results)

        logger.warning("Unrecognized trigger - this Lambda has no API Gateway route")
        return log_and_generate_error_response(
            ErrorCode.INVALID_JSON, "Unrecognized trigger source", 400,
            ValueError("Expected an EventBridge event or a backfill-mode invocation")
        )

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
        # NOTE: ErrorCode has no DATABASE_ERROR constant (fetch_retail_invoices references
        # one that doesn't exist - not replicating that here); INTERNAL_SERVER_ERROR instead.
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Database error", 500, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
