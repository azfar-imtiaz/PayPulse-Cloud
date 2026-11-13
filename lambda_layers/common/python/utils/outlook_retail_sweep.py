"""
Shared Outlook/Microsoft Graph sweep + Jev classification logic for retail invoice discovery.

Used by both the EventBridge-cron pipeline (fetch_and_classify_outlook_invoices) and the
on-demand, single-category API endpoint (fetch_latest_retail_invoices), mirroring how
utils.retail_sweep serves the Gmail side. Confirmed candidates are uploaded to S3 (tagged
with sweep-origin metadata), which re-triggers parse_retail_invoice for extraction.
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone

import boto3

from utils.secretsmanager_utils import get_outlook_oauth_tokens
from utils.dynamodb_utils import update_last_outlook_sweep_fetch, write_ledger_entry, get_ledger_entry
from utils.outlook_api_utils import (
    create_outlook_client, build_sweep_outlook_query, list_messages, get_email_metadata_light,
    derive_vendor_slug_from_sender, get_message_content, extract_html_from_outlook_message,
    get_pdf_attachment_bytes, LIST_MESSAGES_TIMEOUT_SECONDS, LIST_MESSAGES_MAX_ATTEMPTS
)
from utils.s3_utils import generate_retail_invoice_s3_key, upload_html_to_s3
from utils.exceptions import ClassificationError

from utils.jev_client import classify_email
from utils.gemini_fallback import gemini_category_fallback
from utils.backfill_prefilter import should_prefilter_candidate
from utils.retail_categories import SUPPORTED_CATEGORIES, CATEGORY_DESCRIPTIONS

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Generous enough for real invoice PDFs, cheap guardrail against pathological attachments.
MAX_PDF_ATTACHMENT_BYTES = 8 * 1024 * 1024

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_SWEEP_DAYS = 30

# Hard cap on a single backfill batch's window, enforced before any Graph/Jev/Gemini
# work happens. Mirrors fetch_and_classify_retail_invoices' MAX_BACKFILL_WINDOW_DAYS.
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
            window - only meaningful when backfill_start_date is also set.

    Returns:
        Tuple of (start_date, end_date) in Graph OData ISO 8601 format, e.g.
        "2026-09-01T00:00:00Z"
    """
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if backfill_start_date:
        start_dt = datetime.strptime(backfill_start_date, "%Y-%m-%d")
        start_date = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if backfill_end_date:
            end_date = datetime.strptime(backfill_end_date, "%Y-%m-%d").strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"Backfill mode: sweeping from {start_date} to {end_date}")
        return start_date, end_date

    last_sweep = user.get('last_outlook_sweep_fetch')

    if last_sweep:
        try:
            last_sweep_dt = datetime.fromisoformat(last_sweep.replace('Z', '+00:00'))
            start_date = last_sweep_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"Gap-filling sweep from {start_date} to {end_date} (last sweep: {last_sweep})")
        except ValueError as e:
            logger.warning(f"Invalid last_outlook_sweep_fetch timestamp: {last_sweep}. Using default window. Error: {e}")
            start_date = (datetime.now(timezone.utc) - timedelta(days=default_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        start_date = (datetime.now(timezone.utc) - timedelta(days=default_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"First-time sweep (last {default_days} days): {start_date} to {end_date}")

    return start_date, end_date


def list_sweep_candidates(outlook_client, start_date: str, end_date: str, max_pages: int,
                           excluded_senders: list = None,
                           graph_timeout: float = LIST_MESSAGES_TIMEOUT_SECONDS,
                           graph_max_attempts: int = LIST_MESSAGES_MAX_ATTEMPTS) -> tuple:
    """
    Paginated, oldest-first Graph messages listing over the sweep window.

    Returns:
        Tuple of (message_ids, exhausted, last_received_at). When the page cap is hit
        (exhausted=False), last_received_at is the receivedDateTime of the newest message
        reached, so the caller can advance the watermark there and the next run resumes
        from that point instead of restarting the whole window.
    """
    query_filter = build_sweep_outlook_query(start_date, end_date, excluded_senders=excluded_senders)
    message_ids = []
    last_received_at = None
    next_link = None
    pages_fetched = 0

    while True:
        messages, next_link = list_messages(outlook_client, query_filter, page_url=next_link,
                                            timeout=graph_timeout, max_attempts=graph_max_attempts)
        message_ids.extend(m['id'] for m in messages)
        if messages:
            last_received_at = messages[-1].get('receivedDateTime') or last_received_at
        pages_fetched += 1

        if not next_link:
            return message_ids, True, last_received_at

        if pages_fetched >= max_pages:
            logger.warning(f"Hit MAX_SWEEP_PAGES={max_pages} cap with more pages remaining - "
                            f"partial window, reached messages up to {last_received_at}")
            return message_ids, False, last_received_at


def process_candidate_email(outlook_client, ledger_table, s3_bucket, user_id: str, message_id: str,
                             jev_api_key: str, gemini_api_key: str,
                             noul_threshold: float, choice_confidence_threshold: float,
                             is_backfill: bool = False, prefilter_excluded_domains: set = None,
                             category_filter: str = None) -> str:
    """
    Classify a single candidate email and, if confirmed, upload it to S3 to trigger
    extraction. Writes a ledger row for every final outcome - except that a
    category_filter run (on-demand endpoint) only records category-independent outcomes,
    see retail_sweep.process_candidate_email. Returns the outcome string for counting.
    """
    existing = get_ledger_entry(ledger_table, user_id, message_id)
    if existing:
        return 'skipped_already_classified'

    record_verdicts = category_filter is None

    metadata = get_email_metadata_light(outlook_client, message_id)
    subject, sender, snippet = metadata['subject'], metadata['sender'], metadata['snippet']
    has_attachment = metadata['has_attachment']

    if record_verdicts:
        write_ledger_entry(ledger_table, user_id, message_id, status='pending', provider='outlook')

    if is_backfill and should_prefilter_candidate(sender, prefilter_excluded_domains or set()):
        write_ledger_entry(ledger_table, user_id, message_id, status='rejected_prefilter', provider='outlook')
        return 'rejected_prefilter'

    category_descriptions = CATEGORY_DESCRIPTIONS
    if category_filter:
        category_descriptions = {category_filter: CATEGORY_DESCRIPTIONS[category_filter]}

    try:
        result = classify_email(jev_api_key, subject, sender, snippet, category_descriptions, has_attachment)
    except ClassificationError as e:
        logger.error(f"Classification failed for message {message_id}: {e}")
        if record_verdicts:
            write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed',
                                error_detail=str(e), provider='outlook')
        return 'classification_failed'

    noul_result = result['noul_result']
    choice_category = result['choice_category']
    choice_confidence = result['choice_confidence']
    token_usage = result['token_usage']
    used_gemini_fallback = False

    if noul_result < noul_threshold:
        if record_verdicts:
            write_ledger_entry(ledger_table, user_id, message_id, status='rejected_tier1',
                                noul_result=noul_result, choice_category=choice_category,
                                choice_confidence=choice_confidence, used_gemini_fallback=False,
                                jev_token_usage=token_usage, provider='outlook')
        return 'rejected_tier1'

    if choice_category is None or choice_confidence < choice_confidence_threshold:
        used_gemini_fallback = True
        choice_category = gemini_category_fallback(gemini_api_key, subject, sender, snippet, category_descriptions, has_attachment)

        if choice_category is None:
            if record_verdicts:
                write_ledger_entry(ledger_table, user_id, message_id, status='parked_unclassifiable',
                                    noul_result=noul_result, choice_confidence=choice_confidence,
                                    used_gemini_fallback=True, jev_token_usage=token_usage, provider='outlook')
            return 'parked_unclassifiable'

    if choice_category not in SUPPORTED_CATEGORIES:
        if record_verdicts:
            write_ledger_entry(ledger_table, user_id, message_id, status='parked_unsupported_category',
                                noul_result=noul_result, choice_category=choice_category,
                                choice_confidence=choice_confidence, used_gemini_fallback=used_gemini_fallback,
                                jev_token_usage=token_usage, provider='outlook')
        return 'parked_unsupported_category'

    # Confirmed candidate - fetch full content and hand off to the existing extraction Lambda
    message_json = get_message_content(outlook_client, message_id)
    html_content = extract_html_from_outlook_message(message_json)

    if not html_content:
        write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed',
                            choice_category=choice_category, choice_confidence=choice_confidence,
                            used_gemini_fallback=used_gemini_fallback, jev_token_usage=token_usage,
                            error_detail="No HTML content found in message", provider='outlook')
        return 'no_html_content'

    pdf_bytes = get_pdf_attachment_bytes(outlook_client, message_id) if has_attachment else None
    if pdf_bytes and len(pdf_bytes) > MAX_PDF_ATTACHMENT_BYTES:
        logger.warning(f"PDF attachment for message {message_id} is {len(pdf_bytes)} bytes, "
                        f"exceeds MAX_PDF_ATTACHMENT_BYTES={MAX_PDF_ATTACHMENT_BYTES} - skipping attachment, "
                        f"falling back to HTML-only extraction")
        pdf_bytes = None

    received_date_str = message_json.get('receivedDateTime')
    if received_date_str:
        email_date = datetime.fromisoformat(received_date_str.replace('Z', '+00:00'))
    else:
        email_date = datetime.now(timezone.utc)

    vendor_slug = derive_vendor_slug_from_sender(sender)
    s3_key = generate_retail_invoice_s3_key(
        user_id=user_id, vendor_id=vendor_slug, sub_type=choice_category,
        email_date=email_date, message_id=message_id
    )

    upload_html_to_s3(s3_client, s3_bucket, s3_key, html_content,
                       metadata={'source': 'sweep', 'message_id': message_id, 'provider': 'outlook'})

    if pdf_bytes:
        pdf_s3_key = s3_key[:-len('.html')] + '.pdf'
        s3_client.put_object(Bucket=s3_bucket, Key=pdf_s3_key, Body=pdf_bytes)
        logger.info(f"Uploaded sibling PDF attachment to {pdf_s3_key} ({len(pdf_bytes)} bytes)")

    write_ledger_entry(ledger_table, user_id, message_id, status='pending',
                        noul_result=noul_result, choice_category=choice_category,
                        choice_confidence=choice_confidence, used_gemini_fallback=used_gemini_fallback,
                        jev_token_usage=token_usage, s3_path=s3_key, provider='outlook')
    return 'uploaded_for_extraction'


def process_user_sweep(user: dict, backfill_start_date: str = None, backfill_end_date: str = None,
                        max_pages: int = None, category_filter: str = None, since: datetime = None,
                        graph_timeout: float = LIST_MESSAGES_TIMEOUT_SECONDS,
                        graph_max_attempts: int = LIST_MESSAGES_MAX_ATTEMPTS,
                        stop_at_monotonic: float = None) -> dict:
    """
    Run the full sweep + classify flow for a single user's Outlook inbox. The on-demand
    endpoint passes since (exact window start - Graph filters at second granularity, unlike
    Gmail), category_filter, a tighter Graph budget and stop_at_monotonic (a time.monotonic()
    deadline after which remaining messages are left unrecorded for the cron sweep); such
    runs never move the watermark.
    """
    user_id = user['UserID']
    users_table = dynamodb.Table(os.environ['USERS_TABLE'])
    ledger_table = dynamodb.Table(os.environ['RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE'])

    max_pages = max_pages or int(os.environ.get('MAX_SWEEP_PAGES', '10'))
    noul_threshold = float(os.environ.get('NOUL_THRESHOLD', '0.5'))
    choice_confidence_threshold = float(os.environ.get('CHOICE_CONFIDENCE_THRESHOLD', '0.6'))

    if since:
        start_date = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        start_date, end_date = determine_sweep_date_range(user, backfill_start_date=backfill_start_date,
                                                            backfill_end_date=backfill_end_date)
    is_bounded_run = bool(backfill_start_date or since)

    oauth_data = get_outlook_oauth_tokens(user_id, region=os.environ['REGION'])
    outlook_client = create_outlook_client(
        user_id=user_id,
        access_token=oauth_data['access_token'],
        refresh_token=oauth_data['refresh_token'],
        client_id=os.environ.get('OUTLOOK_OAUTH_CLIENT_ID', ''),
        client_secret=os.environ.get('OUTLOOK_OAUTH_CLIENT_SECRET', ''),
        region=os.environ['REGION'],
        expires_at=oauth_data.get('expires_at')
    )

    is_backfill = is_bounded_run
    prefilter_excluded_domains = {
        d.strip().lower() for d in os.environ.get('BACKFILL_PREFILTER_EXCLUDED_DOMAINS', '').split(',') if d.strip()
    }

    excluded_senders = [s.strip() for s in os.environ.get('EXCLUDED_SENDER_EMAILS', '').split(',') if s.strip()]
    message_ids, exhausted, last_received_at = list_sweep_candidates(
        outlook_client, start_date, end_date, max_pages, excluded_senders=excluded_senders,
        graph_timeout=graph_timeout, graph_max_attempts=graph_max_attempts
    )
    logger.info(f"Sweep found {len(message_ids)} candidate messages for user {user_id} "
                f"({start_date} to {end_date}, exhausted={exhausted})")

    outcome_counts = {}
    for message_id in message_ids:
        if stop_at_monotonic is not None and time.monotonic() >= stop_at_monotonic:
            outcome_counts['deferred_time_budget'] = outcome_counts.get('deferred_time_budget', 0) + 1
            continue
        try:
            outcome = process_candidate_email(
                outlook_client=outlook_client, ledger_table=ledger_table,
                s3_bucket=os.environ['S3_BUCKET'], user_id=user_id, message_id=message_id,
                jev_api_key=os.environ['JEV_API_KEY'], gemini_api_key=os.environ['GEMINI_API_KEY'],
                noul_threshold=noul_threshold, choice_confidence_threshold=choice_confidence_threshold,
                is_backfill=is_backfill, prefilter_excluded_domains=prefilter_excluded_domains,
                category_filter=category_filter
            )
        except Exception as e:
            logger.error(f"Error processing message {message_id} for user {user_id}: {e}")
            outcome = 'error'

        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        time.sleep(0.1)  # Rate limiting, matches Gmail sweep's pattern

    # Watermark = end of what was actually covered: the query's end_date (not "now", which
    # would skip mail received while this run was executing) or, if capped, the last
    # message reached. The boundary message is re-listed next run and skipped via ledger.
    if not is_bounded_run:
        new_watermark = end_date if exhausted else last_received_at
        if new_watermark:
            update_last_outlook_sweep_fetch(users_table, user_id, timestamp=new_watermark)

    return {
        'user_id': user_id,
        'candidates_found': len(message_ids),
        'outcome_counts': outcome_counts,
        'date_range': {'start': start_date, 'end': end_date},
        'window_exhausted': exhausted,
    }

