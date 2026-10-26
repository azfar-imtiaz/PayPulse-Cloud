import os
import boto3
import logging
from typing import Dict, Any, Optional
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError

from parser_factory import get_parser_for_subtype, extract_subtype_from_s3_path, extract_vendor_from_filename
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, S3Error
from utils.dynamodb_utils import write_ledger_entry, upsert_retail_invoice_to_dynamodb
from utils.vendor_normalization import resolve_vendor_name


# Configure logging
logging.basicConfig(level=logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')

# Environment variables
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
FOOD_DELIVERY_INVOICES_TABLE = os.environ['FOOD_DELIVERY_INVOICES_TABLE']
CLOTHING_INVOICES_TABLE = os.environ['CLOTHING_INVOICES_TABLE']
TECHNOLOGY_INVOICES_TABLE = os.environ['TECHNOLOGY_INVOICES_TABLE']
SUBSCRIPTION_INVOICES_TABLE = os.environ['SUBSCRIPTION_INVOICES_TABLE']
GROCERY_INVOICES_TABLE = os.environ['GROCERY_INVOICES_TABLE']
MISC_UTILITY_INVOICES_TABLE = os.environ['MISC_UTILITY_INVOICES_TABLE']
MISC_INVOICES_TABLE = os.environ['MISC_INVOICES_TABLE']
TRAVEL_INVOICES_TABLE = os.environ['TRAVEL_INVOICES_TABLE']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
# Only set when this Lambda is wired into the sweep pipeline (Phase 7) - absent in the
# original vendor-driven-only deployment, so default to None rather than a hard KeyError.
RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE = os.environ.get('RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE')
VENDOR_ALIASES_TABLE = os.environ['VENDOR_ALIASES_TABLE']

# DynamoDB table references
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)
ledger_table = dynamodb.Table(RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE) if RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE else None
vendor_aliases_table = dynamodb.Table(VENDOR_ALIASES_TABLE)

# Detail tables mapping
detail_tables = {
    'food-delivery': dynamodb.Table(FOOD_DELIVERY_INVOICES_TABLE),
    'clothing': dynamodb.Table(CLOTHING_INVOICES_TABLE),
    'technology': dynamodb.Table(TECHNOLOGY_INVOICES_TABLE),
    'subscriptions': dynamodb.Table(SUBSCRIPTION_INVOICES_TABLE),
    'grocery': dynamodb.Table(GROCERY_INVOICES_TABLE),
    'utility': dynamodb.Table(MISC_UTILITY_INVOICES_TABLE),
    'miscellaneous': dynamodb.Table(MISC_INVOICES_TABLE),
    'travel': dynamodb.Table(TRAVEL_INVOICES_TABLE)
}


def extract_user_id_from_s3_path(s3_key: str) -> str:
    """
    Extract user ID from S3 object key.

    Expected format: invoices/{user_id}/retail/{sub_type}/{vendor}_{date}_{hash}.html
    """
    try:
        path_parts = s3_key.split('/')
        if len(path_parts) < 2:
            raise ValueError(f"Invalid S3 path format: {s3_key}")

        user_id = path_parts[1]
        logging.info(f"Extracted user_id '{user_id}' from S3 path: {s3_key}")
        return user_id
    except Exception as e:
        logging.error(f"Failed to extract user_id from S3 path '{s3_key}': {e}")
        raise ValueError(f"Invalid S3 path format: {s3_key}") from e


def download_html_from_s3(bucket: str, s3_key: str) -> tuple[str, str]:
    """Download HTML content from S3 and return content with last-modified date."""
    try:
        logging.info(f"Downloading HTML content from S3: {bucket}/{s3_key}")
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        html_content = response['Body'].read().decode('utf-8')

        # Extract last-modified date and format as ISO 8601 date string
        last_modified = response['LastModified']
        fallback_date = last_modified.strftime('%Y-%m-%d')

        logging.info(f"Successfully downloaded HTML content ({len(html_content)} characters)")
        logging.info(f"S3 object last-modified date: {fallback_date}")
        return html_content, fallback_date
    except Exception as e:
        logging.error(f"Failed to download HTML from S3: {e}")
        raise S3Error(f"Failed to download HTML from S3: {bucket}/{s3_key}") from e


def get_sweep_source_metadata(bucket: str, s3_key: str) -> Optional[Dict[str, str]]:
    """
    Check whether the triggering S3 object was uploaded by the new sweep/classification
    pipeline (fetch_and_classify_retail_invoices), vs. the original vendor-driven
    fetch_retail_invoices pipeline.

    The sweep pipeline tags its uploads with x-amz-meta-source=sweep and
    x-amz-meta-message-id=<gmail message id>. Vendor-driven uploads have no such tags,
    so this returns None for them - callers should skip all ledger logic in that case,
    making this a zero-behavior-change addition for the existing pipeline.

    Returns:
        {'message_id': str} if this is a sweep-sourced object, else None.
    """
    try:
        head = s3_client.head_object(Bucket=bucket, Key=s3_key)
        object_metadata = head.get('Metadata', {})
    except ClientError as e:
        logging.warning(f"Could not read S3 object metadata for {s3_key}: {e}")
        return None

    if object_metadata.get('source') != 'sweep':
        return None

    message_id = object_metadata.get('message_id')
    if not message_id:
        logging.warning(f"Sweep-tagged object {s3_key} is missing message_id metadata")
        return None

    return {'message_id': message_id}


def lambda_handler(event, context):
    """
    Main Lambda handler for parsing retail invoices.

    Triggered by S3 uploads of HTML files to retail invoice paths.
    """
    user_id = None
    message_id = None

    try:
        # Extract S3 event details
        s3_event = event['Records'][0]['s3']
        bucket = s3_event['bucket']['name']
        s3_key_raw = s3_event['object']['key']

        # URL-decode the S3 key to handle special characters like & in filenames
        s3_key = unquote_plus(s3_key_raw)

        logging.info(f"Processing retail invoice: {bucket}/{s3_key}")
        if s3_key != s3_key_raw:
            logging.info(f"URL-decoded S3 key from: {s3_key_raw}")

        # Extract metadata from S3 path
        user_id = extract_user_id_from_s3_path(s3_key)
        sub_type = extract_subtype_from_s3_path(s3_key)
        vendor_name = extract_vendor_from_filename(s3_key)

        logging.info(f"Extracted metadata - User: {user_id}, Sub-type: {sub_type}, Vendor: {vendor_name}")

        # Determine whether this upload came from the new sweep pipeline (needs ledger
        # write-back) or the original vendor-driven pipeline (no ledger row, no-op below).
        sweep_metadata = get_sweep_source_metadata(bucket, s3_key)
        discovery_source = 'sweep' if sweep_metadata else 'vendor_config'
        message_id = sweep_metadata['message_id'] if sweep_metadata else None

        # Download HTML content from S3 and get fallback date
        html_content, fallback_date = download_html_from_s3(bucket, s3_key)

        # Check for a sibling PDF attachment uploaded alongside the HTML (same base key,
        # .pdf extension) - present when the source email had a PDF attachment.
        pdf_bytes = None
        if s3_key.endswith('.html'):
            pdf_s3_key = s3_key[:-len('.html')] + '.pdf'
            try:
                pdf_obj = s3_client.get_object(Bucket=bucket, Key=pdf_s3_key)
                pdf_bytes = pdf_obj['Body'].read()
                logging.info(f"Found sibling PDF attachment: {pdf_s3_key} ({len(pdf_bytes)} bytes)")
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchKey':
                    raise

        # Get appropriate parser for sub-type
        parser = get_parser_for_subtype(sub_type, GEMINI_API_KEY)

        # Create extraction prompt
        prompt = parser.create_extraction_prompt(html_content, vendor_name)

        # Parse invoice using Gemini API
        logging.info(f"Parsing invoice using {parser.__class__.__name__}")
        parsed_data = parser.parse_invoice(html_content, prompt, pdf_bytes=pdf_bytes)

        if not parsed_data:
            logging.error("Failed to parse invoice - Gemini API returned no data")
            if message_id and ledger_table:
                write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed',
                                    error_detail="Gemini API parsing failed")
            return log_and_generate_error_response(
                ErrorCode.INTERNAL_SERVER_ERROR,
                "Failed to parse retail invoice",
                500,
                Exception("Gemini API parsing failed")
            )

        parsed_data['vendor_name'] = resolve_vendor_name(parsed_data.get('vendor_name'), vendor_aliases_table)

        # Per base_parser.py's extraction instructions, Gemini returns 0 for any numeric
        # field it couldn't find in the email - so total_amount == 0 is "I found no amount,"
        # which strongly correlates with this being a non-invoice lifecycle email
        # (shipping/delivery confirmation, etc.).
        # Skip the DB insert, keep the S3 HTML (cheap, useful as future training data).
        total_amount = parsed_data.get('total_amount')
        if total_amount is None or total_amount == 0:
            logging.info(
                f"Skipping DB insert for vendor '{vendor_name}' - total_amount is "
                f"{total_amount!r}, likely a non-invoice lifecycle email rather than a real charge"
            )
            if message_id and ledger_table:
                write_ledger_entry(ledger_table, user_id, message_id, status='rejected_zero_amount',
                                    error_detail="total_amount was zero or missing after extraction")
            return success_response(
                message="Email skipped - no billable amount found, not treated as a real invoice",
                data={'sub_type': sub_type, 'vendor_name': vendor_name, 'outcome': 'rejected_zero_amount'}
            )

        # Insert or upsert parsed data into DynamoDB
        invoice_id, outcome = upsert_retail_invoice_to_dynamodb(
            retail_invoices_table=retail_invoices_table,
            detail_tables=detail_tables,
            invoice_data=parsed_data,
            user_id=user_id,
            sub_type=sub_type,
            s3_path=s3_key,
            fallback_date=fallback_date,
            discovery_source=discovery_source
        )

        logging.info(f"Successfully processed retail invoice with ID: {invoice_id} (outcome: {outcome})")

        if message_id and ledger_table:
            ledger_status = 'duplicate_skipped' if outcome == 'duplicate_skipped' else 'extracted'
            write_ledger_entry(ledger_table, user_id, message_id, status=ledger_status,
                                order_id=parsed_data.get('order_id'), retail_invoice_id=invoice_id,
                                s3_path=s3_key)

        return success_response(
            message=f"Retail invoice parsed and stored successfully",
            data={'invoice_id': invoice_id, 'sub_type': sub_type, 'vendor_name': vendor_name, 'outcome': outcome}
        )

    except ValueError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invalid S3 path format",
            400,
            e
        )

    except S3Error as e:
        if message_id and ledger_table:
            write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed', error_detail=str(e))
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Error downloading HTML from S3",
            502,
            e
        )

    except DatabaseError as e:
        if message_id and ledger_table:
            write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed', error_detail=str(e))
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice processing",
            502,
            e
        )

    except Exception as e:
        if message_id and ledger_table:
            write_ledger_entry(ledger_table, user_id, message_id, status='extraction_failed', error_detail=str(e))
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            "Internal server error during retail invoice parsing",
            500,
            e
        )