import boto3
import logging
from uuid import uuid4
from typing import Dict, Tuple
from collections import defaultdict
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

from utils.utility_functions import postprocess_invoices
from utils.exceptions import UserNotFoundError, UserAlreadyExistsError, DatabaseError, NoInvoiceFoundError


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


def fetch_user_by_id(users_table, user_id: str) -> dict:
    response = users_table.get_item(Key={'UserID': user_id})
    
    if 'Item' not in response:
        logging.info(f"User with ID '{user_id}' not found.")
        raise UserNotFoundError("User not found")
    
    logging.info(f"User '{user_id}' fetched successfully from DB!")
    return response['Item']


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


def get_user_rental_invoices(dynamodb_table, user_id: str) -> Tuple[Dict, int]:
    # This returns all rental invoices for a given user
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        invoices = response.get('Items', [])
        invoices_grouped_by_year = postprocess_invoices(invoices)
        logging.info(f"Retrieved {len(invoices)} rental invoices for user '{user_id}'")
        return invoices_grouped_by_year, len(invoices)
    except Exception as e:
        raise DatabaseError(f"Error getting rental invoices for '{user_id}'") from e


def get_invoice_details(dynamodb_table, user_id: str, invoice_id: str) -> Dict:
    # This function returns the details for a given invoice ID
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id) & Key('InvoiceID').eq(invoice_id)
        )
        invoices = response.get('Items', [])
        if len(invoices) == 0:
            logging.warning(f"No invoice found for user '{user_id}' and invoice '{invoice_id}'")
            raise ValueError(f"No invoice found for this user and invoice ID!")
        return invoices[0]
    except ValueError as e:
        raise NoInvoiceFoundError from e
    except Exception as e:
        raise DatabaseError from e


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
    logging.info(f"Searching for invoices in month {current_month} and year {current_year} for user '{user_id}'")
    response = dynamodb_table.scan(
        FilterExpression=(Attr('UserID').eq(user_id) &
                          Attr('due_date_year').eq(str(current_year)) &
                          Attr('due_date_month').eq(str(current_month)))
    )
    items_found = response.get('Items', [])
    logging.info(f"Found {len(items_found)} items in the table!")
    for item in items_found:
        print(item)
    return len(items_found) > 0


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


def get_active_vendors(vendor_config_table) -> list:
    """
    Scan VendorConfig table for all active vendors

    Args:
        vendor_config_table: DynamoDB table resource for VendorConfig

    Returns:
        List of vendor configurations (dictionaries)
    """
    try:
        response = vendor_config_table.scan(
            FilterExpression=Attr('active').eq(True)
        )
        vendors = response.get('Items', [])
        logging.info(f"Found {len(vendors)} active vendors")
        return vendors
    except ClientError as e:
        raise DatabaseError("Error retrieving active vendors from VendorConfig") from e


def update_last_retail_invoice_fetch(users_table, user_id: str) -> None:
    """
    Update user's last_retail_invoice_fetch timestamp to current time

    Args:
        users_table: DynamoDB table resource for Users
        user_id: User ID
    """
    try:
        current_timestamp = datetime.now(timezone.utc).isoformat()

        users_table.update_item(
            Key={'UserID': user_id},
            UpdateExpression='SET last_retail_invoice_fetch = :timestamp',
            ExpressionAttributeValues={
                ':timestamp': current_timestamp
            }
        )

        logging.info(f"Updated last_retail_invoice_fetch for user {user_id}: {current_timestamp}")
    except ClientError as e:
        raise DatabaseError(f"Error updating last_retail_invoice_fetch for user {user_id}") from e


def delete_user_retail_invoices(retail_invoices_table, user_id: str) -> list:
    """
    Delete all retail invoices for a user from the RetailInvoices table

    Args:
        retail_invoices_table: DynamoDB table resource for RetailInvoices
        user_id: User ID

    Returns:
        List of invoice IDs that were deleted (needed for detail table cleanup)
    """
    try:
        # Get all retail invoices for this user_id
        response = retail_invoices_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        invoices = response['Items']
        invoice_ids = []

        # Delete all retail invoices one-by-one and collect invoice IDs
        for item in invoices:
            invoice_id = item['InvoiceID']
            retail_invoices_table.delete_item(
                Key={'UserID': user_id, 'InvoiceID': invoice_id}
            )
            invoice_ids.append(invoice_id)

        logging.info(f"{len(invoices)} retail invoices deleted for user '{user_id}'!")
        return invoice_ids
    except ClientError as e:
        raise DatabaseError(f"Error deleting retail invoices for '{user_id}'") from e


def delete_retail_invoice_details(detail_tables_dict: Dict, invoice_ids: list) -> None:
    """
    Delete retail invoice details from all detail tables using invoice IDs

    Args:
        detail_tables_dict: Dictionary mapping table names to DynamoDB table resources
        invoice_ids: List of invoice IDs to delete from detail tables
    """
    try:
        total_deleted = 0
        for table_name, table_resource in detail_tables_dict.items():
            deleted_count = 0
            for invoice_id in invoice_ids:
                try:
                    # Try to delete from this detail table (may not exist in all tables)
                    table_resource.delete_item(
                        Key={'InvoiceID': invoice_id}
                    )
                    deleted_count += 1
                except ClientError as e:
                    # If item doesn't exist, that's okay - not all invoices exist in all detail tables
                    if e.response['Error']['Code'] != 'ResourceNotFoundException':
                        logging.warning(f"Error deleting invoice {invoice_id} from {table_name}: {e}")

            total_deleted += deleted_count
            logging.info(f"Deleted {deleted_count} items from {table_name}")

        logging.info(f"Total {total_deleted} detail records deleted across all retail invoice detail tables")
    except Exception as e:
        raise DatabaseError(f"Error deleting retail invoice details: {str(e)}") from e
