import os
import json
import boto3
import logging
from decimal import Decimal

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from parser_factory import get_parser_for_subtype

from utils.decorators import require_auth
from utils.dynamodb_utils import get_retail_invoice_for_user
from utils.s3_utils import get_valid_retail_categories
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, NoInvoiceFoundError, S3Error

logging.basicConfig(level=logging.INFO)

dynamodb = boto3.resource('dynamodb')
dynamodb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')
serializer = TypeSerializer()

# Environment variables
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
BUCKET_NAME = os.environ['BUCKET_NAME']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

FOOD_DELIVERY_INVOICES_TABLE = os.environ['FOOD_DELIVERY_INVOICES_TABLE']
CLOTHING_INVOICES_TABLE = os.environ['CLOTHING_INVOICES_TABLE']
TECHNOLOGY_INVOICES_TABLE = os.environ['TECHNOLOGY_INVOICES_TABLE']
SUBSCRIPTION_INVOICES_TABLE = os.environ['SUBSCRIPTION_INVOICES_TABLE']
GROCERY_INVOICES_TABLE = os.environ['GROCERY_INVOICES_TABLE']
MISC_UTILITY_INVOICES_TABLE = os.environ['MISC_UTILITY_INVOICES_TABLE']
MISC_INVOICES_TABLE = os.environ['MISC_INVOICES_TABLE']
TRAVEL_INVOICES_TABLE = os.environ['TRAVEL_INVOICES_TABLE']

retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)

# Sub-type to detail table name mapping
SUBTYPE_TO_TABLE_NAME = {
    'food-delivery': FOOD_DELIVERY_INVOICES_TABLE,
    'clothing': CLOTHING_INVOICES_TABLE,
    'technology': TECHNOLOGY_INVOICES_TABLE,
    'subscriptions': SUBSCRIPTION_INVOICES_TABLE,
    'grocery': GROCERY_INVOICES_TABLE,
    'utility': MISC_UTILITY_INVOICES_TABLE,
    'miscellaneous': MISC_INVOICES_TABLE,
    'travel': TRAVEL_INVOICES_TABLE
}


@require_auth
def lambda_handler(event, context, user_id):
    """Recategorize a retail invoice - requires JWT authentication"""
    try:
        path_parameters = event.get('pathParameters', {}) or {}
        invoice_id = path_parameters.get('invoice_id')

        if not invoice_id:
            return log_and_generate_error_response(
                ErrorCode.MISSING_FIELDS,
                "invoice_id is required in path parameters",
                400,
                None
            )

        body = json.loads(event.get('body') or '{}')
        new_sub_type = body.get('new_sub_type')

        if not new_sub_type:
            return log_and_generate_error_response(
                ErrorCode.MISSING_FIELDS,
                "new_sub_type is required in the request body",
                400,
                None
            )

        valid_categories = get_valid_retail_categories()
        if new_sub_type not in valid_categories:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                f"Invalid new_sub_type '{new_sub_type}'. Valid options: {', '.join(valid_categories)}",
                400,
                None
            )

        logging.info(f"Attempting to recategorize invoice '{invoice_id}' for user '{user_id}' to '{new_sub_type}'")

        # Step 1: Fetch invoice and validate ownership
        invoice = get_retail_invoice_for_user(retail_invoices_table, user_id, invoice_id)
        old_sub_type = invoice.get('sub_type')
        s3_path = invoice.get('s3_path')
        vendor_name = invoice.get('vendor_name')

        # No-op if already in the target category
        if old_sub_type == new_sub_type:
            return success_response(
                message="Invoice is already in the requested category",
                data={
                    "invoice_id": invoice_id,
                    "old_sub_type": old_sub_type,
                    "new_sub_type": new_sub_type
                }
            )

        if not s3_path:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invoice has no associated S3 file to re-parse",
                400,
                None
            )

        # Step 2: Re-fetch original HTML from S3
        html_content = download_html_from_s3(BUCKET_NAME, s3_path)

        # Step 3: Re-parse with the new sub-type's parser
        parser = get_parser_for_subtype(new_sub_type, GEMINI_API_KEY)
        prompt = parser.create_extraction_prompt(html_content, vendor_name)
        parsed_data = parser.parse_invoice(html_content, prompt)

        if not parsed_data:
            logging.error(f"Gemini re-parse failed for invoice '{invoice_id}' into sub-type '{new_sub_type}'")
            return log_and_generate_error_response(
                ErrorCode.INVOICE_PARSE_ERROR,
                "Failed to re-parse invoice for the new category - invoice left unchanged",
                502,
                Exception("Gemini API parsing failed")
            )

        # Step 4: Build the new detail-table item from the freshly parsed data
        detail_data = parsed_data.copy()
        detail_data['InvoiceID'] = invoice_id
        base_fields = ['vendor_name', 'total_amount', 'currency', 'invoice_date', 'order_id']
        for field in base_fields:
            detail_data.pop(field, None)

        new_detail_table_name = SUBTYPE_TO_TABLE_NAME.get(new_sub_type)
        old_detail_table_name = SUBTYPE_TO_TABLE_NAME.get(old_sub_type)

        # Step 5: Atomically update base table + move the detail row
        new_total_amount = parsed_data.get('total_amount', invoice.get('total_amount'))
        transact_recategorize(
            user_id=user_id,
            invoice_id=invoice_id,
            new_sub_type=new_sub_type,
            new_total_amount=_convert_floats_to_decimal(new_total_amount),
            old_detail_table_name=old_detail_table_name,
            new_detail_table_name=new_detail_table_name,
            new_detail_item=_convert_floats_to_decimal(detail_data)
        )

        logging.info(f"Successfully recategorized invoice '{invoice_id}' from '{old_sub_type}' to '{new_sub_type}'")

        return success_response(
            message="Invoice recategorized successfully",
            data={
                "invoice_id": invoice_id,
                "old_sub_type": old_sub_type,
                "new_sub_type": new_sub_type
            }
        )

    except NoInvoiceFoundError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invoice not found or you don't have permission to recategorize it",
            404,
            e
        )

    except S3Error as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Error downloading invoice file from S3",
            502,
            e
        )

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice recategorization",
            502,
            e
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except Exception as e:
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            500,
            e
        )


def _convert_floats_to_decimal(value):
    """DynamoDB rejects native floats - Gemini's parsed output (prices, quantities) needs
    converting to Decimal before being written via put_item/TransactWriteItems."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _convert_floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_floats_to_decimal(v) for v in value]
    return value


def download_html_from_s3(bucket: str, s3_key: str) -> str:
    """Re-download the original invoice HTML from S3 for re-parsing."""
    try:
        logging.info(f"Downloading HTML content from S3: {bucket}/{s3_key}")
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logging.error(f"Failed to download HTML from S3: {e}")
        raise S3Error(f"Failed to download HTML from S3: {bucket}/{s3_key}") from e


def transact_recategorize(user_id: str, invoice_id: str, new_sub_type: str, new_total_amount,
                           old_detail_table_name: str, new_detail_table_name: str, new_detail_item: dict) -> None:
    """
    Atomically: update the RetailInvoices base item's sub_type/UserID_SubType (and
    total_amount, since re-parsing into a new category can yield a different amount),
    delete the old detail-table row, and put the freshly parsed new detail-table row.

    Using a single TransactWriteItems call avoids a partial failure leaving sub_type
    pointing at a category with no corresponding detail row.
    """
    transact_items = [
        {
            'Update': {
                'TableName': RETAIL_INVOICES_TABLE,
                'Key': {
                    'UserID': {'S': user_id},
                    'InvoiceID': {'S': invoice_id}
                },
                'UpdateExpression': 'SET sub_type = :new_sub_type, UserID_SubType = :new_composite, total_amount = :new_total_amount',
                'ExpressionAttributeValues': {
                    ':new_sub_type': serializer.serialize(new_sub_type),
                    ':new_composite': serializer.serialize(f"{user_id}_{new_sub_type}"),
                    ':new_total_amount': serializer.serialize(new_total_amount)
                }
            }
        }
    ]

    if old_detail_table_name:
        transact_items.append({
            'Delete': {
                'TableName': old_detail_table_name,
                'Key': {
                    'InvoiceID': {'S': invoice_id}
                }
            }
        })

    if new_detail_table_name:
        transact_items.append({
            'Put': {
                'TableName': new_detail_table_name,
                'Item': {k: serializer.serialize(v) for k, v in new_detail_item.items()}
            }
        })

    try:
        dynamodb_client.transact_write_items(TransactItems=transact_items)
    except ClientError as e:
        logging.error(f"TransactWriteItems failed for invoice '{invoice_id}': {e}")
        raise DatabaseError(f"Error recategorizing invoice '{invoice_id}'") from e
