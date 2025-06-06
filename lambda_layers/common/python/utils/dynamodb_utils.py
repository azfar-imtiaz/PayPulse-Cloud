import boto3
import logging
from uuid import uuid4
from typing import Dict, List
from collections import defaultdict
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

from utils.utility_functions import remove_user_id_from_invoices
from utils.exceptions import UserNotFoundError, UserAlreadyExistsError, DatabaseError


def fetch_user_by_email(users_table, email: str) -> dict:
    response = users_table.query(
        IndexName="Email-index",
        KeyConditionExpression=Key('Email').eq(email)
    )

    if not response['Items']:
        logging.info(f"User with email '{email}' not found.")
        raise UserNotFoundError("Invalid credentials")

    logging.info("User fetched successfully from DB!")
    return response['Items'][0]


def create_user_in_dynamodb(dynamodb, email: str, name: str, password: str, users_table_name: str) -> str:
    """
    This function creates an entry for a new user in the Users table. It's triggered when a new user signs up.
    """
    from utils.auth_utils import create_password_hash

    def generate_random_user_id() -> str:
        """
        This function is only used when creating a new user
        """
        return f"user_{uuid4()}"

    creation_date = str(datetime.now(timezone.utc).date())
    creation_time = str(datetime.now(timezone.utc).time())
    dynamodb_resource = boto3.resource('dynamodb')
    table = dynamodb_resource.Table(users_table_name)

    # check if user already exists
    try:
        _ = fetch_user_by_email(table, email=email)
        raise UserAlreadyExistsError(f"User with email '{email}' already exists.")
    except UserNotFoundError:
        try:
            user_id = generate_random_user_id()
            hashed_password_str = create_password_hash(password)
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
            return user_id
        except ClientError as e:
            logging.error(f"Error creating user '{email}' in DynamoDB: {e}")
            raise DatabaseError(f"Error creating new user: '{email}'") from e


def delete_user_in_dynamodb(dynamodb_table, user_id: str):
    try:
        dynamodb_table.delete_item(Key={'UserID': user_id})
        logging.info(f"User '{user_id}' deleted successfully!")
    except Exception as e:
        raise DatabaseError(f"Error deleting user '{user_id}'") from e


def is_invoice_already_parsed(current_month: int, current_year: int, invoice_dates: defaultdict) -> bool:
    """
    This function checks if an invoice with the current month and year exists in the provided defaultdict
    """
    '''
    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    response = table.query(
        IndexName='due_date_year-due_date_month-index',
        KeyConditionExpression=Key('due_date_year').eq(current_year) & Key('due_date_month').eq(current_month)
    )
    return len(response.get('Items', [])) > 0
    '''
    return invoice_dates[current_year][current_month]


def get_user_rental_invoices(dynamodb_table, user_id: str) -> List:
    # This returns all rental invoices for a given user
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        invoices = response.get('Items', [])
        invoices = remove_user_id_from_invoices(invoices)
        logging.info(f"Retrieved {len(invoices)} rental invoices for user '{user_id}'")
        return invoices
    except Exception as e:
        raise DatabaseError(f"Error getting rental invoices for '{user_id}'") from e


def get_all_invoice_dates(dynamodb_table, user_id: str) -> defaultdict:
    """
    This function get the month and year for all invoices in the DynamoDB table belonging to this user, and returns them as a defaultdict
    """
    response = dynamodb_table.scan(
        ProjectionExpression="due_date_month, due_date_year",
        FilterExpression=Attr('UserID').eq(user_id)
    )
    invoices = response['Items']

    while 'LastEvaluatedKey' in response:
        response = dynamodb_table.scan(
            ProjectionExpression="due_date_month, due_date_year",
            FilterExpression=Attr('UserID').eq(user_id),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        invoices.extend(response['Items'])

    invoice_dates = defaultdict(lambda: defaultdict(lambda: False))
    for invoice in invoices:
        year = invoice['due_date_year']
        month = invoice ['due_date_month']
        invoice_dates[year][month] = True
    return invoice_dates


def invoice_exists_in_dynamodb(dynamodb_table, user_id: str, current_month: int, current_year: int) -> bool:
    """
    This function checks if an invoice with the current month and year exists in the RentalInvoices DynamoDB table
    """
    '''
    response = table.query(
        IndexName='due_date_year-due_date_month-index',
        KeyConditionExpression=Key('due_date_year').eq(current_year) & Key('due_date_month').eq(current_month)
    )
    '''
    response = dynamodb_table.scan(
        FilterExpression=(Key('UserID').eq(user_id) &
                          Key('due_date_year').eq(current_year) &
                          Key('due_date_month').eq(current_month))
    )
    return len(response.get('Items', [])) > 0


def create_invoice_in_dynamodb(dynamodb_table, invoice_id: str, user_id: str, parsed_data: Dict):
    """
    This function creates a new entry in the RentalInvoices DB table. It is triggered when a new rental invoice is found.
    """
    parsed_data['InvoiceID'] = invoice_id
    parsed_data['UserID'] = user_id
    # insert parsed invoice into table
    dynamodb_table.put_item(Item=parsed_data)


def delete_user_invoices(dynamodb_table, user_id: str):
    try:
        # get all invoices for this user_id
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        invoices = response['Items']
        # delete all these invoices one-by-one
        # TODO: This can be improved by a batch delete operation later?
        for item in invoices:
            dynamodb_table.delete_item(
                Key={'UserID': user_id, 'InvoiceID': item['InvoiceID']}
            )
        logging.info(f"{len(invoices)} invoices deleted for user '{user_id}'!")
    except ClientError as e:
        raise DatabaseError(f"Error deleting invoices for '{user_id}'") from e
