import os
import json
import boto3
import logging

from utils.decorators import require_auth
from utils.dynamodb_utils import get_invoice_details
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError, NoInvoiceFoundError


dynamodb = boto3.resource('dynamodb')

INVOICES_TABLE = os.environ['INVOICES_TABLE']

invoices_table = dynamodb.Table(INVOICES_TABLE)


@require_auth
def lambda_handler(event, context, user_id):
    """Get rental invoice details by ID - requires JWT authentication"""
    try:

        invoice_type = event['pathParameters'].get('type')
        invoice_id = event['pathParameters'].get('invoice_id')
        logging.info(f"Received invoice request with type {invoice_type} and ID: {invoice_id}")

        invoice = get_invoice_details(invoices_table, user_id=user_id, invoice_id=invoice_id)
        logging.info(f"Parsed invoice details: {invoice}")
        return success_response(
            message="Invoice details retrieved successfully!",
            data=invoice
        )

    except NoInvoiceFoundError as e:
        return success_response(
            message=f"Missing data: {str(e)}",
            status_code=204
        )

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, "Missing fields in URL", 400, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice retrieval",
            502,
            e
        )

    except TypeError as e:
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            "Encountered decimal value in response",
            500,
            e
        )

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)