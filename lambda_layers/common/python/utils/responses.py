import json
import logging

from utils.utility_functions import convert_decimal_to_int


class ErrorCode:
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    GMAIL_TOKEN_EXPIRED = "GMAIL_TOKEN_EXPIRED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"
    JWT_ERROR = "JWT_ERROR"
    INVALID_JSON = "INVALID_JSON"
    MISSING_FIELDS = "MISSING_FIELDS"
    INVOICE_PARSE_ERROR = "INVOICE_PARSE_ERROR"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


def success_response(message: str, data=None, status_code: int = 200):
    return {
        'statusCode': status_code,
        'headers': {"Content-Type": "application/json"},
        'body': json.dumps({
            'message': message,
            'code': status_code,
            'data': data
        },
        default=convert_decimal_to_int)
    }


def error_response(code: ErrorCode, message: str, status_code: int = 500):
    return {
        'statusCode': status_code,
        'headers': {"Content-Type": "application/json"},
        'body': json.dumps({
            'error': {
                'code': code,
                'message': message
            }
        })
    }


def log_and_generate_error_response(code: ErrorCode, message: str, status_code: int = 500, error=None):
    if error:
        logging.error(f"{code}: {message} | Exception: {error}")
    return error_response(code, message, status_code)
