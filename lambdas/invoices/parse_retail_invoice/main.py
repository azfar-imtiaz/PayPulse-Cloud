import os
import boto3
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Dict, Any
from urllib.parse import unquote_plus

from parser_factory import get_parser_for_subtype, extract_subtype_from_s3_path, extract_vendor_from_filename
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, S3Error


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
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# DynamoDB table references
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)

# Detail tables mapping
detail_tables = {
    'food-delivery': dynamodb.Table(FOOD_DELIVERY_INVOICES_TABLE),
    'clothing': dynamodb.Table(CLOTHING_INVOICES_TABLE),
    'technology': dynamodb.Table(TECHNOLOGY_INVOICES_TABLE),
    'subscriptions': dynamodb.Table(SUBSCRIPTION_INVOICES_TABLE),
    'grocery': dynamodb.Table(GROCERY_INVOICES_TABLE),
    'utility': dynamodb.Table(MISC_UTILITY_INVOICES_TABLE),
    'miscellaneous': dynamodb.Table(MISC_INVOICES_TABLE)
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


def insert_retail_invoice_to_dynamodb(invoice_data: Dict[str, Any], user_id: str, sub_type: str, s3_path: str, fallback_date: str) -> str:
    """
    Insert parsed retail invoice data into DynamoDB tables.

    Args:
        invoice_data: Parsed invoice data from Gemini
        user_id: User ID
        sub_type: Retail invoice sub-type
        s3_path: S3 path to the original HTML file

    Returns:
        Generated invoice ID
    """
    try:
        invoice_id = generate_invoice_id()
        created_at = datetime.now(timezone.utc).isoformat()

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

        # Prepare base retail invoice data
        base_invoice_data = {
            'UserID': user_id,
            'InvoiceID': invoice_id,
            'vendor_name': invoice_data.get('vendor_name'),
            'sub_type': sub_type,
            'total_amount': invoice_data.get('total_amount'),
            'currency': invoice_data.get('currency'),
            'invoice_date': invoice_date,
            'created_at': created_at,
            's3_path': s3_path,
            'order_id': invoice_data.get('order_id'),
            'payment_status': 'completed',  # Default status
            'UserID_SubType': f"{user_id}_{sub_type}"  # For GSI-2
        }

        # Insert into RetailInvoices base table
        logging.info(f"Inserting base invoice data into {RETAIL_INVOICES_TABLE}")
        retail_invoices_table.put_item(Item=base_invoice_data)

        # Prepare detail table data (exclude base fields)
        detail_data = invoice_data.copy()
        detail_data['InvoiceID'] = invoice_id

        # Remove base fields from detail data to avoid duplication
        base_fields = ['vendor_name', 'total_amount', 'currency', 'invoice_date', 'order_id']
        for field in base_fields:
            detail_data.pop(field, None)

        # Insert into appropriate detail table
        detail_table = detail_tables.get(sub_type)
        if detail_table:
            logging.info(f"Inserting detail data into {detail_table.table_name}")
            detail_table.put_item(Item=detail_data)
        else:
            logging.warning(f"No detail table found for sub_type: {sub_type}")

        logging.info(f"Successfully inserted retail invoice with ID: {invoice_id}")
        return invoice_id

    except Exception as e:
        logging.error(f"Failed to insert retail invoice into DynamoDB: {e}")
        raise DatabaseError(f"Failed to insert retail invoice: {str(e)}") from e


def lambda_handler(event, context):
    """
    Main Lambda handler for parsing retail invoices.

    Triggered by S3 uploads of HTML files to retail invoice paths.
    """
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
            return log_and_generate_error_response(
                ErrorCode.INTERNAL_SERVER_ERROR,
                "Failed to parse retail invoice",
                500,
                Exception("Gemini API parsing failed")
            )

        # Insert parsed data into DynamoDB
        invoice_id = insert_retail_invoice_to_dynamodb(
            invoice_data=parsed_data,
            user_id=user_id,
            sub_type=sub_type,
            s3_path=s3_key,
            fallback_date=fallback_date
        )

        logging.info(f"Successfully processed retail invoice with ID: {invoice_id}")

        return success_response(
            message=f"Retail invoice parsed and stored successfully",
            data={'invoice_id': invoice_id, 'sub_type': sub_type, 'vendor_name': vendor_name}
        )

    except ValueError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invalid S3 path format",
            400,
            e
        )

    except S3Error as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Error downloading HTML from S3",
            502,
            e
        )

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice processing",
            502,
            e
        )

    except Exception as e:
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            "Internal server error during retail invoice parsing",
            500,
            e
        )