import os
import json
import boto3
import logging

from botocore.exceptions import ClientError

from utils.decorators import require_auth
from utils.dynamodb_utils import get_retail_invoice_for_user
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, NoInvoiceFoundError

logging.basicConfig(level=logging.INFO)

dynamodb = boto3.resource('dynamodb')

RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)


@require_auth
def lambda_handler(event, context, user_id):
    """Mark a retail invoice as a duplicate of another - requires JWT authentication"""
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
        duplicate_of_invoice_id = body.get('duplicate_of_invoice_id')

        if not duplicate_of_invoice_id:
            return log_and_generate_error_response(
                ErrorCode.MISSING_FIELDS,
                "duplicate_of_invoice_id is required in the request body",
                400,
                None
            )

        if duplicate_of_invoice_id == invoice_id:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "An invoice cannot be marked as a duplicate of itself",
                400,
                None
            )

        logging.info(
            f"Attempting to mark invoice '{invoice_id}' as a duplicate of '{duplicate_of_invoice_id}' "
            f"for user '{user_id}'"
        )

        # Step 1: Fetch both invoices, ownership-checked
        duplicate_invoice = get_retail_invoice_for_user(retail_invoices_table, user_id, invoice_id)
        original_invoice = get_retail_invoice_for_user(retail_invoices_table, user_id, duplicate_of_invoice_id)

        # Step 2: Reject chaining - the "original" must not itself be a marked duplicate
        if original_invoice.get('is_duplicate'):
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "The target invoice is itself marked as a duplicate - point to its original instead",
                400,
                None
            )

        # Step 3: Validate matching sub_type and total_amount
        if duplicate_invoice.get('sub_type') != original_invoice.get('sub_type'):
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invoices must have the same category to be marked as duplicates",
                400,
                None
            )

        if duplicate_invoice.get('total_amount') != original_invoice.get('total_amount'):
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invoices must have the same total amount to be marked as duplicates",
                400,
                None
            )

        if duplicate_invoice.get('discovery_source') != original_invoice.get('discovery_source'):
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invoices must come from the same discovery source to be marked as duplicates",
                400,
                None
            )

        # Step 4: Mark the duplicate invoice
        mark_as_duplicate(user_id, invoice_id, duplicate_of_invoice_id)

        logging.info(f"Successfully marked invoice '{invoice_id}' as a duplicate of '{duplicate_of_invoice_id}'")

        return success_response(
            message="Invoice marked as duplicate successfully",
            data={
                "invoice_id": invoice_id,
                "duplicate_of_invoice_id": duplicate_of_invoice_id,
                "sub_type": duplicate_invoice.get('sub_type'),
                "total_amount": duplicate_invoice.get('total_amount')
            }
        )

    except NoInvoiceFoundError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invoice not found or you don't have permission to access it",
            404,
            e
        )

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error while marking invoice as duplicate",
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


def mark_as_duplicate(user_id: str, invoice_id: str, duplicate_of_invoice_id: str) -> None:
    try:
        retail_invoices_table.update_item(
            Key={'UserID': user_id, 'InvoiceID': invoice_id},
            UpdateExpression='SET is_duplicate = :true, duplicate_of_invoice_id = :original_id',
            ExpressionAttributeValues={
                ':true': True,
                ':original_id': duplicate_of_invoice_id
            }
        )
    except ClientError as e:
        logging.error(f"Error marking invoice '{invoice_id}' as duplicate: {e}")
        raise DatabaseError(f"Error marking invoice '{invoice_id}' as duplicate") from e
