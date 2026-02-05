import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.dynamodb_utils import get_user_rental_invoices, get_user_retail_invoices, get_user_retail_invoices_by_subtype, get_retail_invoice_details
from utils.s3_utils import get_valid_retail_categories
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, \
    DatabaseError, NoInvoiceFoundError


dynamodb = boto3.resource('dynamodb')

RENTAL_INVOICES_TABLE = os.environ['RENTAL_INVOICES_TABLE']
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
JWT_SECRET = os.environ['JWT_SECRET']

rental_invoices_table = dynamodb.Table(RENTAL_INVOICES_TABLE)
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)


def get_retail_detail_table_name(sub_type: str) -> str:
    """
    Map retail invoice sub-type to its corresponding detail table name
    """
    subtype_to_table = {
        'food-delivery': 'FoodDeliveryInvoices',
        'clothing': 'ClothingInvoices',
        'technology': 'TechnologyInvoices',
        'subscriptions': 'SubscriptionInvoices',
        'grocery': 'GroceryInvoices',
        'utility': 'MiscellaneousUtilityInvoices',
        'miscellaneous': 'MiscellaneousInvoices',
        'travel': 'TravelInvoices'
    }

    if sub_type not in subtype_to_table:
        raise ValueError(f"Invalid retail sub-type: {sub_type}")

    return subtype_to_table[sub_type]


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

        # Extract invoice type from path parameters and subtype/invoice-id from query parameters
        path_parameters = event.get('pathParameters', {}) or {}
        query_parameters = event.get('queryStringParameters', {}) or {}
        invoice_type = path_parameters.get('type')
        invoice_subtype = query_parameters.get('subtype')
        invoice_id = query_parameters.get('invoice-id')

        # Validate invoice type
        if invoice_type not in ['rental', 'retail']:
            return log_and_generate_error_response(
                ErrorCode.INVALID_REQUEST,
                f"Invalid invoice type '{invoice_type}'. Must be 'rental' or 'retail'",
                400,
                None
            )

        # Handle rental invoices
        if invoice_type == 'rental':
            if invoice_subtype or invoice_id:
                return log_and_generate_error_response(
                    ErrorCode.INVALID_REQUEST,
                    "Rental invoices do not support sub-type filtering or detail lookup",
                    400,
                    None
                )

            invoices, invoices_count = get_user_rental_invoices(rental_invoices_table, user_id=user_id)
            message_prefix = "Rental"

        # Handle retail invoices
        else:
            if invoice_subtype:
                # Validate sub-type
                valid_categories = get_valid_retail_categories()
                if invoice_subtype not in valid_categories:
                    return log_and_generate_error_response(
                        ErrorCode.INVALID_REQUEST,
                        f"Invalid retail sub-type '{invoice_subtype}'. Valid options: {', '.join(valid_categories)}",
                        400,
                        None
                    )

                # Check if invoice-id is also provided for detail lookup
                if invoice_id:
                    # Get detailed invoice information from the corresponding detail table
                    detail_table_name = get_retail_detail_table_name(invoice_subtype)
                    detail_table = dynamodb.Table(detail_table_name)

                    invoice_details = get_retail_invoice_details(detail_table, invoice_id)

                    return success_response(
                        message=f"Retail {invoice_subtype} invoice details retrieved successfully!",
                        data={
                            "invoiceDetails": invoice_details
                        }
                    )
                else:
                    # Get summary list of invoices for the sub-type
                    invoices, invoices_count = get_user_retail_invoices_by_subtype(
                        retail_invoices_table, user_id=user_id, sub_type=invoice_subtype
                    )
                    message_prefix = f"Retail {invoice_subtype}"
            else:
                # invoice_id without subtype is not allowed
                if invoice_id:
                    return log_and_generate_error_response(
                        ErrorCode.INVALID_REQUEST,
                        "invoice-id parameter requires subtype parameter to be specified",
                        400,
                        None
                    )

                invoices, invoices_count = get_user_retail_invoices(retail_invoices_table, user_id=user_id)
                message_prefix = "Retail"

        # Return response
        if invoices_count > 0:
            return success_response(
                message=f"{message_prefix} invoices retrieved successfully!",
                data={
                    "invoiceCount": invoices_count,
                    "invoices": invoices
                }
            )
        else:
            logging.info(f"No {message_prefix.lower()} invoices found for user {user_id}")
            return success_response(
                message=f"No {message_prefix.lower()} invoices found for this user."
            )

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except InvalidTokenError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_TOKEN, "Malformed Token", 401, e)

    except TokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.TOKEN_EXPIRED, "Expired token", 401, e)

    except JWTDecodingError as e:
        return log_and_generate_error_response(ErrorCode.JWT_ERROR, "Error parsing JWT token", 500, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except NoInvoiceFoundError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_REQUEST,
            "Invoice not found",
            404,
            e
        )

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