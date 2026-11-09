import os
import json
import boto3
import logging
import calendar

from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict

from utils.decorators import require_auth
from utils.dynamodb_utils import get_rental_invoice_for_month, get_retail_invoices_for_month
from utils.utility_functions import build_rental_invoice_card, build_retail_invoice_card
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import DatabaseError

LOCAL_TIMEZONE = ZoneInfo("Europe/Stockholm")

dynamodb = boto3.resource('dynamodb')

RENTAL_INVOICES_TABLE = os.environ['RENTAL_INVOICES_TABLE']
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']

rental_invoices_table = dynamodb.Table(RENTAL_INVOICES_TABLE)
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)


def parse_month_param(month_param: str):
    """Parse a 'YYYY-MM' string into (year, month) ints, defaulting to the current Stockholm month."""
    if month_param:
        year_str, month_str = month_param.split('-')
        return int(year_str), int(month_str)
    today_local = datetime.now(LOCAL_TIMEZONE).date()
    return today_local.year, today_local.month


@require_auth
def lambda_handler(event, context, user_id):
    """Get the current (or specified) month's rental + retail spend summary for the home screen - requires JWT authentication"""
    try:
        query_parameters = event.get('queryStringParameters', {}) or {}
        month_param = query_parameters.get('month')
        include_items = query_parameters.get('include', '').lower() == 'items'

        try:
            year, month = parse_month_param(month_param)
        except (ValueError, AttributeError) as e:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                "Invalid 'month' parameter. Expected format: YYYY-MM",
                400,
                e
            )

        start_date = f"{year:04d}-{month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year:04d}-{month:02d}-{last_day:02d}"

        rental_invoice = get_rental_invoice_for_month(rental_invoices_table, user_id=user_id, year=year, month=month)
        retail_invoices = get_retail_invoices_for_month(
            retail_invoices_table, user_id=user_id, start_date=start_date, end_date=end_date
        )

        rental_summary = build_rental_invoice_card(rental_invoice) if rental_invoice else None

        retail_total = sum(invoice.get('total_amount', 0) for invoice in retail_invoices)
        retail_currency = next((invoice.get('currency') for invoice in retail_invoices if invoice.get('currency')), None)
        by_subtype = defaultdict(lambda: 0)
        for invoice in retail_invoices:
            by_subtype[invoice.get('sub_type', 'unknown')] += invoice.get('total_amount', 0)

        retail_summary = {
            "total_amount": retail_total,
            "currency": retail_currency,
            "count": len(retail_invoices),
            "by_subtype": dict(by_subtype)
        }
        if include_items:
            retail_summary["items"] = [build_retail_invoice_card(invoice) for invoice in retail_invoices]

        return success_response(
            message="Invoice summary retrieved successfully!",
            data={
                "month": f"{year:04d}-{month:02d}",
                "rental": rental_summary,
                "retail": retail_summary
            }
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during invoice summary retrieval",
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
