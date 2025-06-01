import os
import json
import boto3
import logging

from utils.jwt_utils import get_user_id_from_token
from utils.dynamodb_utils import get_user_rental_invoices
from utils.error_handling import log_and_generate_error_response
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

        invoices = get_user_rental_invoices(invoices_table, user_id=user_id)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'{len(invoices)} rental invoices retrieved',
                'invoices': invoices
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
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return log_and_generate_error_response(error_code=500, error_message="Internal Server Error", error=e)