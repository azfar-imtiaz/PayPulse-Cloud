import os

import jwt
import time
import json
import boto3
import bcrypt
import logging

from typing import Union
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])
jwt_secret = os.environ['JWT_SECRET']

# TODO: This function is defined in both signup and login. Implement this in a utils file somewhere
def log_and_generate_error_response(error_code: int, error_message: str, error: Exception = None) -> dict:
    logging.error(error_message)
    response_body = {'message': error_message}
    if error:
        response_body['error'] = str(error)
    return {
        'statusCode': error_code,
        'body': json.dumps(response_body)
    }


def fetch_user_by_email(email: str) -> dict:
    response = users_table.query(
        IndexName="Email-index",
        KeyConditionExpression=Key('Email').eq(email)
    )

    if not response['Items']:
        return log_and_generate_error_response(
            error_code=401,
            error_message="Invalid credentials"
        )
    logging.info("User fetched successfully from DB!")
    return response['Items'][0]


def verify_user_password(user_password: str, db_password: str) -> Union[dict, None]:
    if not bcrypt.checkpw(user_password.encode('utf-8'), db_password.encode('utf-8')):
        return log_and_generate_error_response(
            error_code=401,
            error_message="Invalid credentials"
        )
    logging.info("Password verified successfully!")
    return None


def generate_jwt_token(user_id: str, email: str) -> Union[dict, str]:
    try:
        payload = {
            "user_id": user_id,
            "email": email,
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400     # 24 hours
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    except Exception as e:
        return log_and_generate_error_response(
            error_code=500,
            error_message="An error was encountered generating the JWT token",
            error=e
        )
    logging.info("Token generated successfully!")
    return token


def lambda_handler(event, context):
    # TODO: Error handling needs to be improved. Errors need to be thrown by the functions above, and handled with logging here
    user_info = json.loads(event['body'])

    email = user_info['email']
    password = user_info['password']

    user = fetch_user_by_email(email=email)
    try:
        db_password = user['Password']
    except KeyError:
        # this means an error was encountered in fetching the user's information from DB
        return user

    response = verify_user_password(user_password=password, db_password=db_password)
    if response is not None:
        return response

    token = generate_jwt_token(user_id=user['UserID'], email=email)
    if type(token) is dict:
        # this means an error was encountered in generating the JWT token
        return token

    return {
        "statusCode": 200,
        "body": json.dumps({
            "token": token
        })
    }
