import os
import json
import boto3
import logging

from utils.decorators import require_auth
from utils.dynamodb_utils import get_user_rental_invoices, get_recent_retail_invoices
from utils.utility_functions import build_rental_invoice_card, build_retail_invoice_card
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError

MAX_LIMIT = 20
DEFAULT_LIMIT = 5

dynamodb = boto3.resource('dynamodb')

RENTAL_INVOICES_TABLE = os.environ['RENTAL_INVOICES_TABLE']
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']

rental_invoices_table = dynamodb.Table(RENTAL_INVOICES_TABLE)
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)


def rental_sort_date(invoice: dict) -> str:
    year = invoice.get('due_date_year', '0000')
    month = str(invoice.get('due_date_month', '00')).zfill(2)
    return f"{year}-{month}-01"


@require_auth
def lambda_handler(event, context, user_id):
    """Get the N most recent invoices (rental + retail combined) for the home screen - requires JWT authentication"""
    try:
        query_parameters = event.get('queryStringParameters', {}) or {}
        try:
            limit = int(query_parameters.get('limit', DEFAULT_LIMIT))
        except ValueError as e:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invalid 'limit' parameter. Must be an integer",
                400,
                e
            )
        limit = max(1, min(limit, MAX_LIMIT))

        # Rental invoices are low-volume per user (~1/month); query the full set and sort locally.
        rental_invoices_by_year, _ = get_user_rental_invoices(rental_invoices_table, user_id=user_id)
        rental_candidates = [invoice for invoices in rental_invoices_by_year.values() for invoice in invoices]
        rental_candidates.sort(key=rental_sort_date, reverse=True)
        rental_candidates = rental_candidates[:MAX_LIMIT]

        retail_candidates = get_recent_retail_invoices(retail_invoices_table, user_id=user_id, limit=MAX_LIMIT)

        merged = (
            [(rental_sort_date(invoice), build_rental_invoice_card(invoice)) for invoice in rental_candidates] +
            [(invoice.get('invoice_date', ''), build_retail_invoice_card(invoice)) for invoice in retail_candidates]
        )
        merged.sort(key=lambda pair: pair[0], reverse=True)
        recent_invoices = [card for _, card in merged[:limit]]

        return success_response(
            message="Recent invoices retrieved successfully!",
            data={
                "invoiceCount": len(recent_invoices),
                "invoices": recent_invoices
            }
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during recent invoices retrieval",
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
