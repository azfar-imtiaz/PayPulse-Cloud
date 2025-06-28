import os
import json
import boto3
import logging

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.dynamodb_utils import fetch_user_by_email
from utils.auth_utils import verify_user_password
from utils.jwt_utils import generate_jwt_token
from utils.exceptions import UserNotFoundError, InvalidCredentialsError, JWTGenerationError

dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])
jwt_secret = os.environ['JWT_SECRET']


def lambda_handler(event, context):
    try:
        user_info = json.loads(event['body'])

        email = user_info['email']
        password = user_info['password']
        logging.info("Received email and password in request body! ")

        user = fetch_user_by_email(users_table, email=email)
        logging.info(f"User '{user['UserID']}' retrieved successfully from DB!")
        db_password = user['Password']

        verify_user_password(user_password=password, db_password=db_password)
        logging.info("Password verified!")

        token = generate_jwt_token(user_id=user['UserID'], email=email, jwt_secret=jwt_secret)

        return success_response(
            message="Login successful!",
            data={
                "username": user['Name'],
                "access_token": token,
                "token_type": "Bearer"
            }
        )

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except UserNotFoundError as e:
        return log_and_generate_error_response(ErrorCode.USER_NOT_FOUND, "User not found", 404, e)

    except JWTGenerationError as e:
        return log_and_generate_error_response(ErrorCode.JWT_ERROR, "Error generating JWT", 500, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)


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