import os
import functools
from utils.jwt_utils import get_user_id_from_token
from utils.responses import log_and_generate_error_response, ErrorCode
from utils.exceptions import InvalidCredentialsError, InvalidTokenError, TokenExpiredError


def require_auth(func):
    """
    Decorator to enforce JWT authentication on Lambda handlers.

    Extracts and validates JWT token from Authorization header.
    Injects user_id as third parameter to the decorated function.

    Catches and handles:
    - InvalidCredentialsError (missing/empty auth header)
    - InvalidTokenError (malformed token)
    - TokenExpiredError (expired token)

    Usage:
        @require_auth
        def lambda_handler(event, context, user_id):
            # user_id is automatically injected by decorator after successful auth
            ...

    Returns:
        Lambda response dict with statusCode, headers, and body
    """
    @functools.wraps(func)
    def wrapper(event, context):
        try:
            auth_header = (event.get('headers') or {}).get('authorization')
            user_id = get_user_id_from_token(auth_header, os.environ['JWT_SECRET'])
            return func(event, context, user_id)
        except InvalidCredentialsError as e:
            return log_and_generate_error_response(
                ErrorCode.INVALID_CREDENTIALS,
                "Invalid Credentials",
                401,
                e
            )
        except InvalidTokenError as e:
            return log_and_generate_error_response(
                ErrorCode.INVALID_TOKEN,
                "Malformed Token",
                401,
                e
            )
        except TokenExpiredError as e:
            return log_and_generate_error_response(
                ErrorCode.TOKEN_EXPIRED,
                "Expired token",
                401,
                e
            )
    return wrapper
