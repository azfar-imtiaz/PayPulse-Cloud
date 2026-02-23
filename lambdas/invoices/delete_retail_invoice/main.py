import os
import boto3
import logging

from utils.decorators import require_auth
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, NoInvoiceFoundError, S3Error

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

# Environment variables
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
BUCKET_NAME = os.environ['BUCKET_NAME']

# Detail table environment variables
FOOD_DELIVERY_INVOICES_TABLE = os.environ['FOOD_DELIVERY_INVOICES_TABLE']
CLOTHING_INVOICES_TABLE = os.environ['CLOTHING_INVOICES_TABLE']
TECHNOLOGY_INVOICES_TABLE = os.environ['TECHNOLOGY_INVOICES_TABLE']
SUBSCRIPTION_INVOICES_TABLE = os.environ['SUBSCRIPTION_INVOICES_TABLE']
GROCERY_INVOICES_TABLE = os.environ['GROCERY_INVOICES_TABLE']
MISC_UTILITY_INVOICES_TABLE = os.environ['MISC_UTILITY_INVOICES_TABLE']
MISC_INVOICES_TABLE = os.environ['MISC_INVOICES_TABLE']
TRAVEL_INVOICES_TABLE = os.environ['TRAVEL_INVOICES_TABLE']

# Initialize tables
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)

# Sub-type to table name mapping
SUBTYPE_TO_TABLE_ENV = {
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
    """Delete a retail invoice - requires JWT authentication"""
    try:
        # Extract invoice_id from path parameters
        path_parameters = event.get('pathParameters', {}) or {}
        invoice_id = path_parameters.get('invoice_id')

        if not invoice_id:
            return log_and_generate_error_response(
                ErrorCode.MISSING_FIELDS,
                "invoice_id is required in path parameters",
                400,
                None
            )

        logging.info(f"Attempting to delete retail invoice '{invoice_id}' for user '{user_id}'")

        # Step 1: Get invoice from base table to validate ownership and get metadata
        invoice = get_retail_invoice_for_deletion(
            retail_invoices_table,
            user_id,
            invoice_id
        )

        # Extract metadata for response and detail table lookup
        sub_type = invoice.get('sub_type')
        vendor_name = invoice.get('vendor_name')
        invoice_date = invoice.get('invoice_date')
        total_amount = invoice.get('total_amount')
        currency = invoice.get('currency', 'SEK')
        s3_path = invoice.get('s3_path')

        logging.info(f"Found invoice: vendor={vendor_name}, sub_type={sub_type}, date={invoice_date}")

        # Step 2: Delete from detail table (if sub_type is valid)
        if sub_type and sub_type in SUBTYPE_TO_TABLE_ENV:
            delete_from_detail_table(sub_type, invoice_id)
        else:
            logging.warning(f"Invoice has invalid or missing sub_type: {sub_type}. Skipping detail table deletion.")

        # Step 3: Delete from base table
        delete_from_retail_invoices_table(retail_invoices_table, user_id, invoice_id)

        # Step 4: Delete from S3 (if s3_path exists)
        if s3_path:
            delete_invoice_from_s3(s3, BUCKET_NAME, s3_path)
        else:
            logging.warning(f"Invoice '{invoice_id}' has no s3_path. Skipping S3 deletion.")

        logging.info(f"Successfully deleted retail invoice '{invoice_id}'")

        # Return success response with deleted invoice metadata
        return success_response(
            message="Invoice deleted successfully",
            data={
                "deleted_invoice": {
                    "invoice_id": invoice_id,
                    "vendor_name": vendor_name,
                    "sub_type": sub_type,
                    "invoice_date": invoice_date,
                    "total_amount": total_amount,
                    "currency": currency
                }
            }
        )

    except NoInvoiceFoundError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invoice not found or you don't have permission to delete it",
            404,
            e
        )

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice deletion",
            502,
            e
        )

    except S3Error as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Error deleting invoice file from S3",
            502,
            e
        )

    except Exception as e:
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            500,
            e
        )


def get_retail_invoice_for_deletion(table, user_id: str, invoice_id: str) -> dict:
    """
    Get retail invoice and validate user ownership

    Args:
        table: DynamoDB table resource for RetailInvoices
        user_id: Authenticated user ID
        invoice_id: Invoice ID to delete

    Returns:
        Invoice item dictionary

    Raises:
        NoInvoiceFoundError: If invoice not found or user doesn't own it
        DatabaseError: If database error occurs
    """
    try:
        from boto3.dynamodb.conditions import Key

        # Query with both UserID and InvoiceID to validate ownership
        response = table.query(
            KeyConditionExpression=Key('UserID').eq(user_id) & Key('InvoiceID').eq(invoice_id)
        )

        invoices = response.get('Items', [])

        if len(invoices) == 0:
            logging.warning(f"No invoice found for user '{user_id}' and invoice '{invoice_id}'")
            raise NoInvoiceFoundError("Invoice not found or access denied")

        logging.info(f"Invoice '{invoice_id}' validated for user '{user_id}'")
        return invoices[0]

    except NoInvoiceFoundError:
        raise
    except Exception as e:
        logging.error(f"Error fetching invoice for deletion: {e}")
        raise DatabaseError("Error validating invoice ownership") from e


def delete_from_detail_table(sub_type: str, invoice_id: str) -> None:
    """
    Delete invoice from corresponding detail table

    Args:
        sub_type: Invoice sub-type (e.g., 'food-delivery')
        invoice_id: Invoice ID to delete

    Raises:
        DatabaseError: If deletion fails
    """
    try:
        from botocore.exceptions import ClientError

        table_name = SUBTYPE_TO_TABLE_ENV.get(sub_type)
        if not table_name:
            logging.warning(f"No detail table mapping for sub_type '{sub_type}'")
            return

        detail_table = dynamodb.Table(table_name)

        # Attempt to delete from detail table
        detail_table.delete_item(Key={'InvoiceID': invoice_id})

        logging.info(f"Deleted invoice '{invoice_id}' from detail table '{table_name}'")

    except ClientError as e:
        # If item doesn't exist in detail table, that's okay (may not have been parsed)
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logging.info(f"Invoice '{invoice_id}' not found in detail table '{table_name}' (may not have been parsed)")
        else:
            logging.error(f"Error deleting from detail table '{table_name}': {e}")
            raise DatabaseError("Error deleting from detail table") from e

    except Exception as e:
        logging.error(f"Unexpected error deleting from detail table: {e}")
        raise DatabaseError("Error deleting invoice details") from e


def delete_from_retail_invoices_table(table, user_id: str, invoice_id: str) -> None:
    """
    Delete invoice from RetailInvoices base table

    Args:
        table: DynamoDB table resource
        user_id: User ID
        invoice_id: Invoice ID to delete

    Raises:
        DatabaseError: If deletion fails
    """
    try:
        table.delete_item(
            Key={'UserID': user_id, 'InvoiceID': invoice_id}
        )
        logging.info(f"Deleted invoice '{invoice_id}' from RetailInvoices table")

    except Exception as e:
        logging.error(f"Error deleting from RetailInvoices table: {e}")
        raise DatabaseError("Error deleting invoice from base table") from e


def delete_invoice_from_s3(s3_client, bucket_name: str, s3_path: str) -> None:
    """
    Delete invoice HTML file from S3

    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        s3_path: S3 object key/path

    Raises:
        S3Error: If deletion fails (except for file not found)
    """
    try:
        from botocore.exceptions import ClientError

        s3_client.delete_object(Bucket=bucket_name, Key=s3_path)
        logging.info(f"Deleted invoice file from S3: {s3_path}")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        # If file doesn't exist, that's okay (idempotent deletion)
        if error_code == 'NoSuchKey' or error_code == '404':
            logging.warning(f"S3 file not found (already deleted?): {s3_path}")
        else:
            logging.error(f"Error deleting from S3: {e}")
            raise S3Error("Error deleting invoice file from S3") from e

    except Exception as e:
        logging.error(f"Unexpected error deleting from S3: {e}")
        raise S3Error("Error deleting invoice file") from e
