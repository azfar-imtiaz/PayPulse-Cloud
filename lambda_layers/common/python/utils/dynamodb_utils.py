import boto3
import bcrypt
import logging
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from utils.exceptions import UserNotFoundError, UserAlreadyExistsError, DatabaseError


def fetch_user_by_email(users_table, email: str) -> dict:
    response = users_table.query(
        IndexName="Email-index",
        KeyConditionExpression=Key('Email').eq(email)
    )

    if not response['Items']:
        logging.warning(f"User with email {email} not found.")
        raise UserNotFoundError("Invalid credentials")

    logging.info("User fetched successfully from DB!")
    return response['Items'][0]


def create_user_in_dynamodb(dynamodb, user_id: str, email: str, name: str, password: str, users_table_name: str):
    creation_date = str(datetime.now(timezone.utc).date())
    creation_time = str(datetime.now(timezone.utc).time())
    dynamodb_resource = boto3.resource('dynamodb')
    table = dynamodb_resource.Table(users_table_name)
    # check if user already exists
    try:
        response = table.get_item(
            Key={'UserID': user_id}
        )
        if 'Item' in response:
            logging.warning(f"User with ID {user_id} already exists.")
            raise UserAlreadyExistsError(f"User with ID {user_id} already exists.")
    except ClientError as e:
        logging.error(f"Error checking user existence for {user_id}: {e}")
        raise DatabaseError(f"Error checking user status for {user_id}: {e}")

    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password_str = hashed_password.decode('utf-8')
        dynamodb.put_item(
            TableName=users_table_name,
            Item={
                'UserID': {'S': user_id},
                'Email': {'S': email},
                'Name': {'S': name},
                'Password': {'S': hashed_password_str},
                'CreatedOn': {'S': creation_date},
                'CreatedAt': {'S': creation_time}
            }
        )
        logging.info(f"User with ID {user_id} created successfully in DynamoDB.")
    except ClientError as e:
        logging.error(f"Error creating user {user_id} in DynamoDB: {e}")
        raise DatabaseError(f"Error creating new user: {user_id}") from e