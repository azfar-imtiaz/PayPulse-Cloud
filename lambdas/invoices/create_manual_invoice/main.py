import os
import json
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, Union, List

import boto3

from utils.jwt_utils import get_user_id_from_token
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import ValidationError, DatabaseError
from utils.invoice_validators import validate_manual_invoice_request
from utils.invoice_generator import generate_manual_invoice_id

# Configure logging
logging.basicConfig(level=logging.INFO)

# AWS clients
dynamodb = boto3.resource('dynamodb')

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
JWT_SECRET = os.environ['JWT_SECRET']

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
    'miscellaneous': dynamodb.Table(MISC_INVOICES_TABLE),
    'travel': dynamodb.Table(TRAVEL_INVOICES_TABLE)
}


def convert_floats_to_decimals(data: Union[Dict[str, Any], List[Any], float, Any]) -> Any:
    """
    Recursively convert all float values to Decimal for DynamoDB compatibility.

    Args:
        data: Data that may contain float values (dict, list, float, or other types)

    Returns:
        Data with all floats converted to Decimals
    """
    if isinstance(data, dict):
        return {key: convert_floats_to_decimals(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_floats_to_decimals(item) for item in data]
    elif isinstance(data, float):
        return Decimal(str(data))
    else:
        return data


def insert_manual_invoice_to_dynamodb(request_data: Dict[str, Any], user_id: str) -> str:
    """
    Insert manual retail invoice data into DynamoDB tables.

    Args:
        request_data: Validated request data containing invoice details
        user_id: User ID from JWT token

    Returns:
        Generated invoice ID
    """
    try:
        invoice_id = generate_manual_invoice_id()
        created_at = datetime.now(timezone.utc).isoformat()
        sub_type = request_data['sub_type']

        # Prepare base retail invoice data
        base_invoice_data = {
            'UserID': user_id,
            'InvoiceID': invoice_id,
            'vendor_name': request_data['vendor_name'],
            'sub_type': sub_type,
            'total_amount': Decimal(request_data['total_amount']),
            'currency': request_data['currency'],
            'invoice_date': request_data['invoice_date'],
            'created_at': created_at,
            'invoice_source': 'manual',  # Mark as manually created
            's3_path': None,  # No S3 file for manual invoices
            'order_id': request_data.get('order_id'),
            'payment_status': request_data.get('payment_status', 'paid'),
            'due_date': request_data.get('due_date'),
            'UserID_SubType': f"{user_id}_{sub_type}"  # For GSI-2
        }

        # Remove None values
        base_invoice_data = {k: v for k, v in base_invoice_data.items() if v is not None}

        # Insert into RetailInvoices base table
        logging.info(f"Inserting base invoice data into {RETAIL_INVOICES_TABLE}")
        retail_invoices_table.put_item(Item=base_invoice_data)

        # Prepare detail table data
        detail_data = request_data.get('details', {}).copy()
        detail_data['InvoiceID'] = invoice_id

        # Insert into appropriate detail table if details provided
        if detail_data and len(detail_data) > 1:
            detail_table = detail_tables.get(sub_type)
            if detail_table:
                # Convert all floats to Decimals for DynamoDB compatibility
                detail_data_converted = convert_floats_to_decimals(detail_data)
                logging.info(f"Inserting detail data into {detail_table.table_name}")
                detail_table.put_item(Item=detail_data_converted)
            else:
                logging.warning(f"No detail table found for sub_type: {sub_type}")

        logging.info(f"Successfully inserted manual invoice with ID: {invoice_id}")
        return invoice_id

    except Exception as e:
        logging.error(f"Failed to insert manual invoice into DynamoDB: {e}")
        raise DatabaseError(f"Failed to insert manual invoice: {str(e)}") from e


def lambda_handler(event, context):
    """
    Main Lambda handler for creating manual retail invoices.

    Expects API Gateway event with JSON body containing invoice data.
    """
    try:
        logging.info(f"Received event: {json.dumps(event, default=str)}")

        # Extract user ID from JWT token
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
        logging.info(f"Processing manual invoice creation for user: {user_id}")

        # Parse request body
        body = json.loads(event.get('body', '{}'))

        # Validate request data
        validate_manual_invoice_request(body)

        # Insert invoice into DynamoDB
        invoice_id = insert_manual_invoice_to_dynamodb(body, user_id)

        # Return success response
        response_data = {
            'invoice_id': invoice_id,
            'sub_type': body['sub_type'],
            'total_amount': body['total_amount'],
            'currency': body['currency'],
            'invoice_date': body['invoice_date'],
            'message': 'Manual invoice created successfully'
        }

        return success_response(response_data)

    except ValidationError as e:
        return log_and_generate_error_response(ErrorCode.VALIDATION_ERROR, str(e))
    except DatabaseError as e:
        return log_and_generate_error_response(ErrorCode.DATABASE_ERROR, str(e))
    except Exception as e:
        logging.error(f"Unexpected error in create_manual_invoice: {e}")
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal server error")