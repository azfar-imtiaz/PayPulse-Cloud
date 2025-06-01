import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.s3_utils import delete_user_folder_in_s3
from utils.dynamodb_utils import delete_user_invoices, delete_user_in_dynamodb
from utils.secretsmanager_utils import delete_email_credentials
from utils.error_handling import log_and_generate_error_response
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

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f"All data for user '{user_id}' deleted successfully!"
            })
        }

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(error_code=401, error_message="Invalid credentials", error=e)
    except InvalidTokenError as e:
        return log_and_generate_error_response(error_code=401, error_message="Invalid token", error=e)
    except TokenExpiredError as e:
        return log_and_generate_error_response(error_code=401, error_message="Expired token", error=e)
    except JWTDecodingError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error decoding JWT token", error=e)
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(error_code=400, error_message="Invalid JSON in request body", error=e)
    except DatabaseError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error deleting user invoices", error=e)
    except SecretsManagerError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error deleting user secrets", error=e)
    except S3Error as e:
        return log_and_generate_error_response(error_code=500, error_message="Error deleting user folder in S3", error=e)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return log_and_generate_error_response(error_code=500, error_message="Internal Server Error", error=e)
