import os
import boto3
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from urllib.parse import unquote_plus
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from parser_factory import get_parser_for_subtype, extract_subtype_from_s3_path, extract_vendor_from_filename
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, S3Error
from utils.dynamodb_utils import write_ledger_entry


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

# DynamoDB table references
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)
ledger_table = dynamodb.Table(RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE) if RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE else None

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


def generate_invoice_id() -> str:
    """Generate unique invoice ID."""
    return f"retail_invoice_{uuid4()}"


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


def resolve_duplicate(existing: Dict[str, Any], new_invoice_date: str) -> str:
    """
    Decide what to do when a (UserID, vendor, order_id) match already exists.

    Default policy (per the design doc): keep the lifecycle email with the latest date -
    an earlier email for the same order is treated as superseded and overwritten in place.
    The fuzzy-match fallback for when order_id can't be resolved is deliberately out of
    scope here - exact-match only for this implementation.

    Returns:
        'update' - overwrite the existing row with the new data
        'skip'    - new data is not newer, discard it as a duplicate
    """
    existing_date = existing.get('invoice_date', '')
    if new_invoice_date and new_invoice_date > existing_date:
        return 'update'
    return 'skip'


def compute_vendor_order_key(vendor_name: str, order_id: str, invoice_date: str) -> Optional[str]:
    """
    Compute the dedup key used on the vendor-order-index GSI.

    Prefers an exact (vendor, order_id) match. When order_id isn't resolvable (e.g. AWS
    billing emails have no order number), falls back to (vendor, day) - day granularity,
    not full timestamp, since the goal is catching lifecycle-email duplicates for the same
    purchase, which land on the same calendar day. Known trade-off: two genuinely separate
    same-vendor purchases on the same day will collide and the second will be treated as a
    duplicate update rather than a new invoice - accepted given no better signal exists
    without order_id.

    Returns None if neither order_id nor invoice_date is available (no dedup key possible).
    """
    if order_id:
        return f"{vendor_name}_{order_id}"
    if invoice_date:
        return f"{vendor_name}_{invoice_date[:10]}"
    return None


def find_existing_invoice(user_id: str, vendor_order_key: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Query the vendor-order-index GSI for an existing invoice with the same vendor_order_key
    (see compute_vendor_order_key for how that key is derived). Returns None if no key could
    be computed, or no match is found.

    Known limitation: pre-existing RetailInvoices rows (written before this GSI existed)
    have no vendor_order_key attribute and are absent from this sparse index - they won't
    be found here. Accepted for the parallel-run/testing period.
    """
    if not vendor_order_key:
        return None

    try:
        response = retail_invoices_table.query(
            IndexName='vendor-order-index',
            KeyConditionExpression=Key('UserID').eq(user_id) & Key('vendor_order_key').eq(vendor_order_key)
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except ClientError as e:
        raise DatabaseError(f"Error querying vendor-order-index for {user_id}/{vendor_order_key}") from e


def upsert_retail_invoice_to_dynamodb(invoice_data: Dict[str, Any], user_id: str, sub_type: str, s3_path: str,
                                       fallback_date: str, discovery_source: str) -> tuple[str, str]:
    """
    Insert or upsert parsed retail invoice data into DynamoDB tables.

    Args:
        invoice_data: Parsed invoice data from Gemini
        user_id: User ID
        sub_type: Retail invoice sub-type
        s3_path: S3 path to the original HTML file
        fallback_date: S3 object's last-modified date, used when invoice_date can't be determined
        discovery_source: 'sweep' or 'vendor_config' - which pipeline discovered this email,
                           recorded on every write so the two pipelines' output stays queryable
                           during the parallel-run comparison period.

    Returns:
        Tuple of (invoice_id, outcome) where outcome is 'inserted', 'updated', or 'duplicate_skipped'
    """
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        vendor_name = invoice_data.get('vendor_name')
        order_id = invoice_data.get('order_id')

        # Use fallback date if invoice_date is missing or None
        invoice_date = invoice_data.get('invoice_date')
        if not invoice_date:
            # try to get the date from S3 path
            try:
                if s3_path.find("/") < 0:
                    raise ValueError
                filename = s3_path.split('/')[-1]       # get filename
                filename_date = filename.split("_")[-2]     # get date (sandwiched between vendor name and hash)
                datetime.strptime(filename_date, '%Y-%m-%d')    # validate date structure
                invoice_date = filename_date
                logging.info(f"Using date from S3 path: {filename_date}")
            except (ValueError, IndexError):
                invoice_date = fallback_date
                logging.info(f"Using S3 last-modified date as fallback for invoice_date: {fallback_date}")
        else:
            logging.info(f"Using parsed invoice_date: {invoice_date}")

        vendor_order_key = compute_vendor_order_key(vendor_name, order_id, invoice_date)
        existing_invoice = find_existing_invoice(user_id, vendor_order_key)

        if existing_invoice:
            decision = resolve_duplicate(existing_invoice, invoice_date)
            if decision == 'skip':
                logging.info(f"Duplicate detected for {user_id}/{vendor_order_key} - skipping")
                return existing_invoice['InvoiceID'], 'duplicate_skipped'
            invoice_id = existing_invoice['InvoiceID']
            logging.info(f"Updating existing invoice {invoice_id} for {user_id}/{vendor_order_key}")
        else:
            invoice_id = generate_invoice_id()

        # Prepare base retail invoice data
        base_invoice_data = {
            'UserID': user_id,
            'InvoiceID': invoice_id,
            'vendor_name': vendor_name,
            'sub_type': sub_type,
            'total_amount': invoice_data.get('total_amount'),
            'currency': invoice_data.get('currency'),
            'invoice_date': invoice_date,
            'created_at': created_at,
            's3_path': s3_path,
            'order_id': order_id,
            'payment_status': 'completed',  # Default status
            'UserID_SubType': f"{user_id}_{sub_type}",  # For GSI-2
            'discovery_source': discovery_source,
        }
        if vendor_order_key:
            base_invoice_data['vendor_order_key'] = vendor_order_key

        # Insert/overwrite RetailInvoices base table row
        logging.info(f"Writing base invoice data into {RETAIL_INVOICES_TABLE}")
        retail_invoices_table.put_item(Item=base_invoice_data)

        # Prepare detail table data (exclude base fields)
        detail_data = invoice_data.copy()
        detail_data['InvoiceID'] = invoice_id

        # Remove base fields from detail data to avoid duplication
        base_fields = ['vendor_name', 'total_amount', 'currency', 'invoice_date', 'order_id']
        for field in base_fields:
            detail_data.pop(field, None)

        # Insert/overwrite appropriate detail table row
        detail_table = detail_tables.get(sub_type)
        if detail_table:
            logging.info(f"Writing detail data into {detail_table.table_name}")
            detail_table.put_item(Item=detail_data)
        else:
            logging.warning(f"No detail table found for sub_type: {sub_type}")

        outcome = 'updated' if existing_invoice else 'inserted'
        logging.info(f"Successfully {outcome} retail invoice with ID: {invoice_id}")
        return invoice_id, outcome

    except DatabaseError:
        raise
    except Exception as e:
        logging.error(f"Failed to upsert retail invoice into DynamoDB: {e}")
        raise DatabaseError(f"Failed to upsert retail invoice: {str(e)}") from e


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

        # Get appropriate parser for sub-type
        parser = get_parser_for_subtype(sub_type, GEMINI_API_KEY)

        # Create extraction prompt
        prompt = parser.create_extraction_prompt(html_content, vendor_name)

        # Parse invoice using Gemini API
        logging.info(f"Parsing invoice using {parser.__class__.__name__}")
        parsed_data = parser.parse_invoice(html_content, prompt)

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