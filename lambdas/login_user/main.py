import os
import json
import boto3
import logging

from utils.error_handling import log_and_generate_error_response
from utils.dynamodb_utils import fetch_user_by_email
from utils.utils import verify_user_password, generate_jwt_token
from utils.exceptions import UserNotFoundError, InvalidCredentialsError, JWTGenerationError

dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])
jwt_secret = os.environ['JWT_SECRET']


def lambda_handler(event, context):
    try:
        user_info = json.loads(event['body'])

        email = user_info['email']
        password = user_info['password']

        user = fetch_user_by_email(users_table, email=email)
        db_password = user['Password']

        verify_user_password(user_password=password, db_password=db_password)

        token = generate_jwt_token(user_id=user['UserID'], email=email, jwt_secret=jwt_secret)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "token": token
            })
        }
    except InvalidCredentialsError as e:
        return log_and_generate_error_response(error_code=401, error_message="Invalid credentials", error=e)
    except UserNotFoundError as e:
        return log_and_generate_error_response(error_code=401, error_message="User not found", error=e)
    except JWTGenerationError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error generating JWT", error=e)
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(error_code=400, error_message="Invalid JSON in request body", error=e)
    except KeyError as e:
        return log_and_generate_error_response(error_code=400, error_message=f"Missing key in request body: {e}", error=e)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return log_and_generate_error_response(error_code=500, error_message="Internal Server Error", error=e)


'''
if __name__ == '__main__':
    response = lambda_handler(event={
        'body': json.dumps({
            "email": "azfar.imtiaz2@live.com",
            "password": "my-password-2"
        })
    }, context={})

    print(response)
'''