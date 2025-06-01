import os
import json
import boto3
import logging

from utils.error_handling import log_and_generate_error_response
from utils.dynamodb_utils import create_user_in_dynamodb
from utils.s3_utils import create_user_folder_in_s3
from utils.secretsmanager_utils import store_email_credentials
from utils.exceptions import InvalidCredentialsError, DatabaseError, UserAlreadyExistsError, S3Error, SecretsManagerError

dynamodb = boto3.client('dynamodb')
secrets_manager = boto3.client('secretsmanager')
s3 = boto3.client('s3')

USERS_TABLE = os.environ['USERS_TABLE']
S3_BUCKET = os.environ['S3_BUCKET']


def lambda_handler(event, context):
    try:
        user_info = json.loads(event['body'])

        # user_id = user_info['user_id']
        email = user_info['email']
        name = user_info['name']
        password = user_info['password']
        gmail_app_password = user_info['gmail_app_password']
        logging.info("Retrieved user information from event body.")

        # 1. Store user information in the DB
        user_id = create_user_in_dynamodb(dynamodb, email, name, password, users_table_name=USERS_TABLE)

        # 2. Create folder for user in S3
        create_user_folder_in_s3(s3, user_id=user_id, s3_bucket_name=S3_BUCKET)

        # 3. Store Gmail credentials in SecretsManager
        store_email_credentials(secrets_manager, user_id, email, gmail_app_password)

        return {
            'statusCode': 201,
            'body': json.dumps({
                'message': 'User signup setup completed successfully.'
            })
        }
    except InvalidCredentialsError as e:
        return log_and_generate_error_response(400, str(e))
    except UserAlreadyExistsError as e:
        return log_and_generate_error_response(403, str(e))
    except DatabaseError as e:
        return log_and_generate_error_response(500, str(e))
    except S3Error as e:
        return log_and_generate_error_response(500, str(e))
    except SecretsManagerError as e:
        return log_and_generate_error_response(500, str(e))
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(400, "Invalid JSON in request body", e)
    except KeyError as e:
        return log_and_generate_error_response(400, f"Missing key in request body: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during signup: {e}")
        return log_and_generate_error_response(500, "Internal Server Error", e)