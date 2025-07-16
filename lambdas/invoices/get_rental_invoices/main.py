import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.dynamodb_utils import get_user_rental_invoices
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, \
    DatabaseError


dynamodb = boto3.resource('dynamodb')

INVOICES_TABLE = os.environ['INVOICES_TABLE']
JWT_SECRET = os.environ['JWT_SECRET']

invoices_table = dynamodb.Table(INVOICES_TABLE)


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

        invoices, invoices_count = get_user_rental_invoices(invoices_table, user_id=user_id)
        if invoices_count > 0:
            return success_response(
                message="Rental invoices retrieved successfully!",
                data={
                    "invoiceCount": invoices_count,
                    "invoices": invoices
                }
            )
        else:
            logging.info(f"No rental invoices found for user {user_id}")
            return success_response(
                message="No rental invoices found for this user."
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