import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.s3_utils import delete_user_folder_in_s3
from utils.dynamodb_utils import delete_user_invoices, delete_user_in_dynamodb
from utils.secretsmanager_utils import delete_email_credentials
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, \
    SecretsManagerError, DatabaseError, S3Error


dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
s3 = boto3.client('s3')

USERS_TABLE = os.environ['USERS_TABLE']
INVOICES_TABLE = os.environ['INVOICES_TABLE']
BUCKET_NAME = os.environ['BUCKET_NAME']
JWT_SECRET = os.environ['JWT_SECRET']

users_table = dynamodb.Table(USERS_TABLE)
invoices_table = dynamodb.Table(INVOICES_TABLE)


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

        # delete all invoices for this user in the RentalInvoices table
        delete_user_invoices(invoices_table, user_id=user_id)

        # delete secrets for this user
        delete_email_credentials(secrets_manager, user_id=user_id)

        # delete the folder for this user in S3
        delete_user_folder_in_s3(s3, user_id=user_id, s3_bucket_name=BUCKET_NAME)

        # delete this user from the Users table
        delete_user_in_dynamodb(users_table, user_id=user_id)

        logging.info(f"All data for user '{user_id}' deleted successfully!")

        return success_response(
            message=f"All data for user {user_id} deleted successfully!"
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
            "Database error during user deletion",
            502,
            e
        )

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error deleting Gmail credentials", 502, e)

    except S3Error as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error deleting S3 folder", 502, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
