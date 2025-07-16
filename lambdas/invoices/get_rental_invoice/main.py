import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.dynamodb_utils import get_invoice_details
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, \
    DatabaseError, NoInvoiceFoundError


dynamodb = boto3.resource('dynamodb')

INVOICES_TABLE = os.environ['INVOICES_TABLE']
JWT_SECRET = os.environ['JWT_SECRET']

invoices_table = dynamodb.Table(INVOICES_TABLE)


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

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

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except InvalidTokenError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_TOKEN, "Malformed Token", 401, e)

    except TokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.TOKEN_EXPIRED, "Expired token", 401, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, "Missing fields in URL", 400, e)

    except JWTDecodingError as e:
        return log_and_generate_error_response(ErrorCode.JWT_ERROR, "Error parsing JWT token", 500, e)

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