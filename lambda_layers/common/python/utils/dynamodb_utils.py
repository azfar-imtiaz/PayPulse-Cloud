import boto3
import logging
from uuid import uuid4
from typing import Dict, Tuple
from collections import defaultdict
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

from utils.utility_functions import postprocess_rental_invoices, postprocess_retail_invoices
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
        invoices_grouped_by_year = postprocess_rental_invoices(invoices)
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


def get_active_vendors(vendor_config_table, category: str = None) -> list:
    """
    Scan VendorConfig table for active vendors, optionally filtered by category

    Args:
        vendor_config_table: DynamoDB table resource for VendorConfig
        category: Optional category filter (e.g., 'travel', 'food-delivery', etc.)
                 If None, returns all active vendors

    Returns:
        List of vendor configurations (dictionaries)
    """
    try:
        # Build filter expression - start with active=True
        filter_expression = Attr('active').eq(True)

        # Add category filter if provided
        if category is not None:
            filter_expression = filter_expression & Attr('invoice_sub_type').eq(category)

        response = vendor_config_table.scan(
            FilterExpression=filter_expression
        )
        vendors = response.get('Items', [])

        if category:
            logging.info(f"Found {len(vendors)} active vendors for category '{category}'")
        else:
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


def get_user_retail_invoices(dynamodb_table, user_id: str) -> Tuple[Dict, int]:
    """
    Get all retail invoices for a given user

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID

    Returns:
        Tuple of (invoices_dict, count)
    """
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id),
            ProjectionExpression="InvoiceID, invoice_date, total_amount, currency, vendor_name, sub_type"
        )
        invoices = response.get('Items', [])
        invoices_grouped = postprocess_retail_invoices(invoices)
        logging.info(f"Retrieved {len(invoices)} retail invoices for user '{user_id}'")
        return invoices_grouped, len(invoices)
    except Exception as e:
        raise DatabaseError(f"Error getting retail invoices for '{user_id}'") from e


def get_user_retail_invoices_by_subtype(dynamodb_table, user_id: str, sub_type: str, group_by: str = 'year') -> Tuple[Dict, int]:
    """
    Get all retail invoices for a given user filtered by sub-type

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        sub_type: Invoice sub-type (e.g., 'food-delivery', 'technology')
        group_by: Grouping strategy - 'year' or 'sub_type' (default: 'year' for sub-type queries)

    Returns:
        Tuple of (invoices_dict, count)
    """
    try:
        # Use GSI-2: sub_type-invoice_date-index
        # Partition key format: UserID_SubType
        user_id_subtype = f"{user_id}_{sub_type}"

        response = dynamodb_table.query(
            IndexName='sub_type-invoice_date-index',
            KeyConditionExpression=Key('UserID_SubType').eq(user_id_subtype),
            ProjectionExpression="InvoiceID, invoice_date, total_amount, currency, vendor_name, sub_type"
        )
        invoices = response.get('Items', [])
        invoices_grouped = postprocess_retail_invoices(invoices, group_by=group_by)
        logging.info(f"Retrieved {len(invoices)} retail invoices for user '{user_id}' with sub-type '{sub_type}' grouped by {group_by}")
        return invoices_grouped, len(invoices)
    except Exception as e:
        raise DatabaseError(f"Error getting retail invoices for '{user_id}' with sub-type '{sub_type}'") from e


def get_retail_invoice_details(detail_table, invoice_id: str) -> Dict:
    """
    Get detailed information for a specific retail invoice from its corresponding detail table

    Args:
        detail_table: DynamoDB table resource for specific retail invoice detail table
        invoice_id: Invoice ID to retrieve

    Returns:
        Dictionary containing detailed invoice information
    """
    try:
        response = detail_table.get_item(
            Key={'InvoiceID': invoice_id}
        )

        if 'Item' not in response:
            logging.warning(f"No invoice details found for invoice ID '{invoice_id}'")
            raise NoInvoiceFoundError(f"No invoice details found for invoice ID '{invoice_id}'")

        logging.info(f"Retrieved invoice details for invoice ID '{invoice_id}'")
        return response['Item']
    except NoInvoiceFoundError:
        raise
    except Exception as e:
        raise DatabaseError(f"Error getting invoice details for '{invoice_id}'") from e


def get_retail_invoice_counts(dynamodb_table, user_id: str) -> Dict[str, int]:
    """
    Get counts of retail invoices for all sub-types for a given user

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID

    Returns:
        Dictionary with sub-type counts: {'food-delivery': 5, 'clothing': 2, ...}
    """
    from utils.s3_utils import get_valid_retail_categories

    try:
        valid_categories = get_valid_retail_categories()
        counts = {}

        # Initialize all categories to 0
        for category in valid_categories:
            counts[category] = 0

        # Query all retail invoices for the user and count by sub_type
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id),
            ProjectionExpression="sub_type"
        )

        # Count invoices by sub_type
        for invoice in response.get('Items', []):
            sub_type = invoice.get('sub_type')
            if sub_type in counts:
                counts[sub_type] += 1

        logging.info(f"Retrieved retail invoice counts for user '{user_id}': {counts}")
        return counts

    except Exception as e:
        raise DatabaseError(f"Error getting retail invoice counts for '{user_id}'") from e


def get_retail_invoice_count_by_subtype(dynamodb_table, user_id: str, sub_type: str) -> Dict[str, int]:
    """
    Get count of retail invoices for a specific sub-type for a given user

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        sub_type: Invoice sub-type (e.g., 'food-delivery', 'technology')

    Returns:
        Dictionary with single sub-type count: {'food-delivery': 5}
    """
    try:
        # Use GSI-2: sub_type-invoice_date-index for efficient filtering
        user_id_subtype = f"{user_id}_{sub_type}"

        response = dynamodb_table.query(
            IndexName='sub_type-invoice_date-index',
            KeyConditionExpression=Key('UserID_SubType').eq(user_id_subtype),
            Select='COUNT'  # Only return the count, not the items
        )

        count = response.get('Count', 0)
        result = {sub_type: count}

        logging.info(f"Retrieved retail invoice count for user '{user_id}' sub-type '{sub_type}': {count}")
        return result

    except Exception as e:
        raise DatabaseError(f"Error getting retail invoice count for '{user_id}' sub-type '{sub_type}'") from e
