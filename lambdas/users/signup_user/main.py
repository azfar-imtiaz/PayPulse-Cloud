import os
import json
import boto3
import logging

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.dynamodb_utils import create_user_in_dynamodb
from utils.jwt_utils import generate_jwt_token
from utils.exceptions import InvalidCredentialsError, DatabaseError, UserAlreadyExistsError, S3Error

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
jwt_secret = os.environ['JWT_SECRET']

USERS_TABLE = os.environ['USERS_TABLE']
S3_BUCKET = os.environ['S3_BUCKET']


def lambda_handler(event, context):
    try:
        user_info = json.loads(event['body'])

        email = user_info['email']
        name = user_info['name']
        password = user_info['password']
        logging.info("Retrieved user information from event body.")

        # 1. Store user information in the DB
        user_id = create_user_in_dynamodb(dynamodb, email, name, password, users_table_name=USERS_TABLE)

        # 2. Create folder for user in S3
        # UPDATE: This is not required anymore as the Gmail secret is now created when
        # user establishes connection with Gmail
        # create_user_folder_in_s3(s3, user_id=user_id, s3_bucket_name=S3_BUCKET)

        # 3. Generate JWT Token (OAuth tokens will be stored separately via /auth/gmail/store-tokens endpoint)
        token = generate_jwt_token(user_id, email, jwt_secret)

        return success_response(
            message="Signup successful!",
            data={
                "username": name,
                "access_token": token,
                "token_type": "Bearer"
            },
            status_code=201
        )

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, str(e), 400, e)

    except UserAlreadyExistsError as e:
        return log_and_generate_error_response(ErrorCode.USER_ALREADY_EXISTS, str(e), 403, e)

    except DatabaseError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Database error during signup", 502, e)

    except S3Error as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error creating S3 folder", 502, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key in request body: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)