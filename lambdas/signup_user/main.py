import os
import json
import bcrypt
from typing import Union

import boto3
import logging
from datetime import datetime, timezone

dynamodb = boto3.client('dynamodb')
secrets_manager = boto3.client('secretsmanager')
s3 = boto3.client('s3')

USERS_TABLE = os.environ['USERS_TABLE']
S3_BUCKET = os.environ['S3_BUCKET']


def log_and_generate_error_response(error_code: int, error_message: str, error: Exception = None) -> dict:
    logging.error(error_message)
    response_body = {'message': error_message}
    if error:
        response_body['error'] = str(error)
    return {
        'statusCode': error_code,
        'body': json.dumps(response_body)
    }


def create_user_in_dynamodb(user_id: str, email: str, name: str, password: str) -> Union[dict, None]:
    creation_date = str(datetime.now(timezone.utc).date())
    creation_time = str(datetime.now(timezone.utc).time())
    dynamodb_resource = boto3.resource('dynamodb')
    table = dynamodb_resource.Table(USERS_TABLE)
    # check if user already exists
    try:
        response = table.get_item(
            Key={'UserID': user_id}
        )
        if 'Item' in response:
            return log_and_generate_error_response(
                error_code=403,
                error_message=f'This user "{user_id}" already exists.'
            )
    except Exception as e:
        return log_and_generate_error_response(
            error_code=500,
            error_message=f'Error checking user status for {user_id}',
            error=e
        )

    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password_str = hashed_password.decode('utf-8')
        dynamodb.put_item(
            TableName=USERS_TABLE,
            Item={
                'UserID': {'S': user_id},
                'Email': {'S': email},
                'Name': {'S': name},
                'Password': {'S': hashed_password_str},
                'CreatedOn': {'S': creation_date},
                'CreatedAt': {'S': creation_time}
            }
        )
        logging.info("User information inserted successfully into DynamoDB.")
        return None
    except Exception as e:
        return log_and_generate_error_response(
            error_code=500,
            error_message=f'Error creating new user: {user_id}',
            error=e
        )


def create_user_folder_in_s3(user_id: str) -> Union[dict, None]:
    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=f"rental-invoices/{user_id}/"
        )
        logging.info("User folder created successfully in S3.")
        return None
    except Exception as e:
        return log_and_generate_error_response(
            error_code=500,
            error_message=f'Error creating S3 folder for user {user_id}',
            error=e
        )


def store_gmail_credentials(user_id: str, email: str, gmail_app_password: str) -> Union[dict, None]:
    try:
        secret_name = f"gmail/user/{user_id}"
        secret_value = json.dumps({
            "GMAIL_USER": email,
            "GMAIL_PASSWORD": gmail_app_password,
            "GMAIL_IMAP_URL": "imap.gmail.com"
        })
        secrets_manager.create_secret(
            Name=secret_name,
            SecretString=secret_value
        )
        logging.info("User secret stored successfully.")
        return None
    except Exception as e:
        return log_and_generate_error_response(
            error_code=500,
            error_message=f'Error creating secret for user {user_id}',
            error=e
        )

def lambda_handler(event, context):
    user_info = json.loads(event['body'])

    user_id = user_info['user_id']
    email = user_info['email']
    name = user_info['name']
    password = user_info['password']
    gmail_app_password = user_info['gmail_app_password']
    # s3_folder_name = email.split('@')[0]
    logging.info("Retrieved user information from event body.")

    # 1. Store user information in the DB
    response = create_user_in_dynamodb(user_id, email, name, password)
    if response is not None:
        return response

    # 2. Create folder for user in S3
    response = create_user_folder_in_s3(user_id)
    if response is not None:
        return response

    # 3. Store Gmail credentials in SecretsManager
    response = store_gmail_credentials(user_id, email, gmail_app_password)
    if response is not None:
        return response

    return {
        'statusCode': 201,
        'body': json.dumps({
            'message': 'User signup setup completed successfully.'
        })
    }