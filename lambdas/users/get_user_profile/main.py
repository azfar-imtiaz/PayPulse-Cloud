import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.dynamodb_utils import fetch_user_by_id
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import InvalidCredentialsError, InvalidTokenError, TokenExpiredError, \
    UserNotFoundError, DatabaseError

dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')
USERS_TABLE = os.environ['USERS_TABLE']
JWT_SECRET = os.environ['JWT_SECRET']
REGION = os.environ['REGION']

users_table = dynamodb.Table(USERS_TABLE)


def check_gmail_connection(user_id: str) -> bool:
    """
    Check if user has Gmail OAuth tokens stored in Secrets Manager.
    
    Returns:
        bool: True if Gmail account is connected, False otherwise
    """
    secret_name = f"gmail/user/{user_id}"
    
    try:
        secretsmanager.get_secret_value(SecretId=secret_name)
        logging.info(f"Gmail secret found for user {user_id}")
        return True
    except secretsmanager.exceptions.ResourceNotFoundException:
        logging.info(f"No Gmail secret found for user {user_id}")
        return False
    except Exception as e:
        logging.error(f"Error checking Gmail secret for user {user_id}: {e}")
        return False


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
        logging.info(f"Retrieved user ID '{user_id}' from JWT token")

        user = fetch_user_by_id(users_table, user_id=user_id)
        logging.info(f"User '{user_id}' retrieved successfully from DB!")

        # Check if Gmail account is connected
        gmail_connected = check_gmail_connection(user_id)
        logging.info(f"Gmail connection status for user {user_id}: {gmail_connected}")

        return success_response(
            message="User profile retrieved successfully",
            data={
                "name": user['Name'],
                "email": user['Email'],
                "created_on": user['CreatedOn'],
                "gmail_account_connected": gmail_connected
            }
        )

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except InvalidTokenError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_TOKEN, "Malformed Token", 401, e)

    except TokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.TOKEN_EXPIRED, "Expired token", 401, e)

    except UserNotFoundError as e:
        return log_and_generate_error_response(ErrorCode.USER_NOT_FOUND, "User not found", 404, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during user retrieval",
            502,
            e
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)