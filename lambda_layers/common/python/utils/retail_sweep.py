"""
Shared broad-sweep + Jev classification logic for retail invoice discovery.

Used by both the EventBridge-cron pipeline (fetch_and_classify_retail_invoices) and the
on-demand, single-category API endpoint (fetch_latest_retail_invoices) so the sweep,
classification, and S3 handoff logic has one source of truth. Confirmed candidates are
uploaded to S3 (tagged with sweep-origin metadata), which re-triggers the existing,
unchanged parse_retail_invoice Lambda to run Gemini extraction and the DB write.
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import boto3

from utils.secretsmanager_utils import get_oauth_tokens
from utils.dynamodb_utils import update_last_retail_sweep_fetch, write_ledger_entry, get_ledger_entry
from utils.gmail_api_utils import (
    create_gmail_service, build_sweep_gmail_query, get_email_metadata_light,
    derive_vendor_slug_from_sender, get_email_content, extract_html_from_email
)
from utils.s3_utils import generate_retail_invoice_s3_key, upload_html_to_s3, extract_pdf_attachment_bytes
from utils.exceptions import ClassificationError

from utils.jev_client import classify_email
from utils.gemini_fallback import gemini_category_fallback
from utils.backfill_prefilter import should_prefilter_candidate
from utils.retail_categories import SUPPORTED_CATEGORIES, CATEGORY_DESCRIPTIONS

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Generous enough for real invoice PDFs, cheap guardrail against pathological attachments.
MAX_PDF_ATTACHMENT_BYTES = 8 * 1024 * 1024

# SUPPORTED_CATEGORIES imported from utils.retail_categories above - that module has zero
# imports so lambdas without jev_layer/google_api_layer attached (get_invoices,
# recategorize_retail_invoice, etc.) can resolve the category list without pulling in this
# whole module's heavy dependencies. Categories here must have an implemented Gemini parser
# in lambda_layers/gemini_parsers/parser_factory.py - any category not listed there parks as
# `parked_unsupported_category` instead of being uploaded for extraction.

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
                             noul_threshold: float, choice_confidence_threshold: float,
                             is_backfill: bool = False, prefilter_excluded_domains: set = None,
                             category_filter: str = None, min_internal_date_ms: int = None) -> str:
    """
    Classify a single candidate email and, if confirmed, upload it to S3 to trigger
    extraction. Writes a ledger row for every outcome. Returns the final/interim status
    string for logging/counting purposes.

    Args:
        category_filter: Optional single category key. When set, only that category (plus
            Jev's built-in "none of these" escape hatch) is offered to classify_email /
            gemini_category_fallback, instead of the full CATEGORY_DESCRIPTIONS - used by
            the on-demand single-category endpoint.
        min_internal_date_ms: Optional epoch-ms cutoff. When set, messages whose actual
            Gmail internalDate predates this are skipped before any Jev/Gemini spend -
            needed because Gmail's after:/before: query operators are day-granularity
            only, so an hour-granularity on-demand window has to be enforced here instead
            of in the query.
    """
    existing = get_ledger_entry(ledger_table, user_id, message_id)
    if existing:
        return 'skipped_already_classified'

    # A category-filtered (on-demand) run only asks "is this a <category> invoice?", so its
    # rejections say nothing about the other categories. Recording them would make the full
    # cron sweep skip the email forever, so such runs only record category-independent
    # outcomes (prefilter, upload, no HTML).
    record_verdicts = category_filter is None

    metadata = get_email_metadata_light(gmail_service, message_id)
    subject, sender, snippet = metadata['subject'], metadata['sender'], metadata['snippet']
    has_attachment = metadata['has_attachment']

    if min_internal_date_ms is not None:
        internal_date_ms = metadata.get('internal_date_ms')
        if internal_date_ms is not None and internal_date_ms < min_internal_date_ms:
            return 'outside_window'

    if record_verdicts:
        write_ledger_entry(ledger_table, user_id, message_id, status='pending')

    if is_backfill and should_prefilter_candidate(sender, prefilter_excluded_domains or set()):
        write_ledger_entry(ledger_table, user_id, message_id, status='rejected_prefilter')
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
                                error_detail=str(e))
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
                                jev_token_usage=token_usage)
        return 'rejected_tier1'

    if choice_category is None or choice_confidence < choice_confidence_threshold:
        used_gemini_fallback = True
        choice_category = gemini_category_fallback(gemini_api_key, subject, sender, snippet, category_descriptions, has_attachment)

        if choice_category is None:
            if record_verdicts:
                write_ledger_entry(ledger_table, user_id, message_id, status='parked_unclassifiable',
                                    noul_result=noul_result, choice_confidence=choice_confidence,
                                    used_gemini_fallback=True, jev_token_usage=token_usage)
            return 'parked_unclassifiable'

    if choice_category not in SUPPORTED_CATEGORIES:
        if record_verdicts:
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

    pdf_bytes = extract_pdf_attachment_bytes(email_content) if has_attachment else None
    if pdf_bytes and len(pdf_bytes) > MAX_PDF_ATTACHMENT_BYTES:
        logger.warning(f"PDF attachment for message {message_id} is {len(pdf_bytes)} bytes, "
                        f"exceeds MAX_PDF_ATTACHMENT_BYTES={MAX_PDF_ATTACHMENT_BYTES} - skipping attachment, "
                        f"falling back to HTML-only extraction")
        pdf_bytes = None

    email_date_str = email_content.get('Date')
    email_date = parsedate_to_datetime(email_date_str) if email_date_str else datetime.now(timezone.utc)

    vendor_slug = derive_vendor_slug_from_sender(sender)
    s3_key = generate_retail_invoice_s3_key(
        user_id=user_id, vendor_id=vendor_slug, sub_type=choice_category,
        email_date=email_date, message_id=message_id
    )

    upload_html_to_s3(s3_client, s3_bucket, s3_key, html_content,
                       metadata={'source': 'sweep', 'message_id': message_id})

    if pdf_bytes:
        pdf_s3_key = s3_key[:-len('.html')] + '.pdf'
        s3_client.put_object(Bucket=s3_bucket, Key=pdf_s3_key, Body=pdf_bytes)
        logger.info(f"Uploaded sibling PDF attachment to {pdf_s3_key} ({len(pdf_bytes)} bytes)")

    write_ledger_entry(ledger_table, user_id, message_id, status='pending',
                        noul_result=noul_result, choice_category=choice_category,
                        choice_confidence=choice_confidence, used_gemini_fallback=used_gemini_fallback,
                        jev_token_usage=token_usage, s3_path=s3_key)
    return 'uploaded_for_extraction'


def process_user_sweep(user: dict, backfill_start_date: str = None, backfill_end_date: str = None,
                        max_pages: int = None, category_filter: str = None,
                        min_internal_date_ms: int = None) -> dict:
    """
    Run the full sweep + classify flow for a single user.

    Args:
        category_filter: Optional single category to restrict classification to (see
            process_candidate_email). Used by the on-demand single-category endpoint;
            the cron/backfill paths leave this unset and classify against all categories.
        min_internal_date_ms: Optional epoch-ms cutoff enforced per-candidate (see
            process_candidate_email) - lets a caller request an hour-granularity window
            on top of a day-granularity backfill_start_date/backfill_end_date pair.
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

    is_backfill = bool(backfill_start_date)
    prefilter_excluded_domains = {
        d.strip().lower() for d in os.environ.get('BACKFILL_PREFILTER_EXCLUDED_DOMAINS', '').split(',') if d.strip()
    }

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
                noul_threshold=noul_threshold, choice_confidence_threshold=choice_confidence_threshold,
                is_backfill=is_backfill, prefilter_excluded_domains=prefilter_excluded_domains,
                category_filter=category_filter, min_internal_date_ms=min_internal_date_ms
            )
        except Exception as e:
            logger.error(f"Error processing message {message_id} for user {user_id}: {e}")
            outcome = 'error'

        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        time.sleep(0.1)  # Rate limiting, matches fetch_retail_invoices' pattern

    # On-demand/category-filtered calls always pass backfill_start_date, so this never
    # advances last_retail_sweep_fetch for those - only the real gap-filling cron path does.
    if exhausted and not backfill_start_date:
        update_last_retail_sweep_fetch(users_table, user_id)

    return {
        'user_id': user_id,
        'candidates_found': len(message_ids),
        'outcome_counts': outcome_counts,
        'date_range': {'start': start_date, 'end': end_date},
        'window_exhausted': exhausted,
    }
