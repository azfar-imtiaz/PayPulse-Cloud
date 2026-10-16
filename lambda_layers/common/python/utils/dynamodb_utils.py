import boto3
import logging
from uuid import uuid4
from decimal import Decimal
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


def update_last_retail_sweep_fetch(users_table, user_id: str) -> None:
    """
    Update user's last_retail_sweep_fetch timestamp to current time.

    Separate field from last_retail_invoice_fetch so the broad-sweep classification
    pipeline doesn't collide with the vendor-driven pipeline while both run in parallel.

    Args:
        users_table: DynamoDB table resource for Users
        user_id: User ID
    """
    try:
        current_timestamp = datetime.now(timezone.utc).isoformat()

        users_table.update_item(
            Key={'UserID': user_id},
            UpdateExpression='SET last_retail_sweep_fetch = :timestamp',
            ExpressionAttributeValues={
                ':timestamp': current_timestamp
            }
        )

        logging.info(f"Updated last_retail_sweep_fetch for user {user_id}: {current_timestamp}")
    except ClientError as e:
        raise DatabaseError(f"Error updating last_retail_sweep_fetch for user {user_id}") from e


def _convert_floats_to_decimal(value):
    """
    Recursively convert native Python floats to Decimal, since boto3's DynamoDB
    resource rejects float values outright ("Float types are not supported. Use
    Decimal types instead."). str()-based conversion avoids binary floating-point
    precision artifacts (e.g. Decimal(0.1) != Decimal("0.1")).
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _convert_floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_floats_to_decimal(v) for v in value]
    return value


def write_ledger_entry(ledger_table, user_id: str, message_id: str, status: str, **fields) -> None:
    """
    Write (or merge-update) a row in the RetailEmailClassificationLedger table.

    Uses update_item with a dynamic SET expression rather than put_item, so a later call
    (e.g. parse_retail_invoice writing the final 'extracted'/'duplicate_skipped' status)
    merges onto the row instead of replacing it outright - preserving fields set by an
    earlier call (noul_result, choice_category, choice_confidence, jev_token_usage, etc.)
    that this later call doesn't know about or isn't re-supplying.

    Args:
        ledger_table: DynamoDB table resource for RetailEmailClassificationLedger
        user_id: User ID
        message_id: Gmail message ID
        status: One of the ledger status enum values (e.g. 'pending', 'rejected_tier1',
                 'parked_unclassifiable', 'parked_unsupported_category', 'duplicate_skipped',
                 'extracted', 'extraction_failed')
        **fields: Any additional ledger attributes to store, e.g. noul_result,
                   choice_category, choice_confidence, used_gemini_fallback, jev_token_usage,
                   order_id, retail_invoice_id, s3_path, error_detail
    """
    try:
        updates = {
            'status': status,
            'classified_at': datetime.now(timezone.utc).isoformat(),
        }
        updates.update({k: _convert_floats_to_decimal(v) for k, v in fields.items() if v is not None})

        set_parts = []
        expression_names = {}
        expression_values = {}
        for key, value in updates.items():
            placeholder_name = f"#{key}"
            placeholder_value = f":{key}"
            set_parts.append(f"{placeholder_name} = {placeholder_value}")
            expression_names[placeholder_name] = key
            expression_values[placeholder_value] = value

        ledger_table.update_item(
            Key={'UserID': user_id, 'MessageID': message_id},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )
        logging.info(f"Wrote ledger entry for user {user_id}, message {message_id}: status={status}")
    except ClientError as e:
        raise DatabaseError(f"Error writing ledger entry for user {user_id}, message {message_id}") from e


def get_ledger_entry(ledger_table, user_id: str, message_id: str) -> dict:
    """
    Fetch a single ledger row, if it exists.

    Used by the sweep to skip messages that have already been classified in a prior run
    (regardless of outcome), avoiding reclassification cost.

    Args:
        ledger_table: DynamoDB table resource for RetailEmailClassificationLedger
        user_id: User ID
        message_id: Gmail message ID

    Returns:
        The ledger item dict, or None if no row exists for this (user_id, message_id).
    """
    try:
        response = ledger_table.get_item(Key={'UserID': user_id, 'MessageID': message_id})
        return response.get('Item')
    except ClientError as e:
        raise DatabaseError(f"Error reading ledger entry for user {user_id}, message {message_id}") from e


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


def _build_retail_list_filter(exclude_sources=None):
    """Base is_duplicate filter, ANDed with discovery_source exclusions if any are given.
    Also requires total_amount > 0 - DynamoDB's type-mismatch comparison rules mean this
    single condition excludes missing, NULL-type, zero, and negative values all at once,
    which keeps malformed rows (failed extractions with no amount) out of list/count
    responses regardless of how they ended up in the table."""
    filter_expr = Attr('is_duplicate').not_exists() | Attr('is_duplicate').eq(False)
    for src in (exclude_sources or []):
        filter_expr = filter_expr & Attr('discovery_source').ne(src)
    filter_expr = filter_expr & Attr('total_amount').gt(0)
    return filter_expr


def get_user_retail_invoices(dynamodb_table, user_id: str, exclude_sources=None) -> Tuple[Dict, int]:
    """
    Get all retail invoices for a given user, optionally excluding given discovery_source values

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        exclude_sources: Optional list of discovery_source values to exclude from results

    Returns:
        Tuple of (invoices_dict, count)
    """
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id),
            FilterExpression=_build_retail_list_filter(exclude_sources),
            ProjectionExpression="InvoiceID, invoice_date, total_amount, currency, vendor_name, sub_type"
        )
        invoices = response.get('Items', [])
        invoices_grouped = postprocess_retail_invoices(invoices)
        logging.info(f"Retrieved {len(invoices)} retail invoices for user '{user_id}'")
        return invoices_grouped, len(invoices)
    except Exception as e:
        raise DatabaseError(f"Error getting retail invoices for '{user_id}'") from e


def get_user_retail_invoices_by_subtype(dynamodb_table, user_id: str, sub_type: str, group_by: str = 'year',
                                         exclude_sources=None) -> Tuple[Dict, int]:
    """
    Get all retail invoices for a given user filtered by sub-type, optionally excluding given
    discovery_source values

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        sub_type: Invoice sub-type (e.g., 'food-delivery', 'technology')
        group_by: Grouping strategy - 'year' or 'sub_type' (default: 'year' for sub-type queries)
        exclude_sources: Optional list of discovery_source values to exclude from results

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
            FilterExpression=_build_retail_list_filter(exclude_sources),
            ProjectionExpression="InvoiceID, invoice_date, total_amount, currency, vendor_name, sub_type"
        )
        invoices = response.get('Items', [])
        invoices_grouped = postprocess_retail_invoices(invoices, group_by=group_by)
        logging.info(f"Retrieved {len(invoices)} retail invoices for user '{user_id}' with sub-type '{sub_type}' grouped by {group_by}")
        return invoices_grouped, len(invoices)
    except Exception as e:
        raise DatabaseError(f"Error getting retail invoices for '{user_id}' with sub-type '{sub_type}'") from e


def get_linked_duplicate_invoice_ids(dynamodb_table, user_id: str, invoice_id: str) -> list:
    """
    Find invoice IDs of any invoices marked as duplicates of the given invoice, so its
    detail view can surface them (the merge UX: duplicates are hidden from the list but
    linked from the original's detail).

    No GSI exists on duplicate_of_invoice_id - per-user invoice volume is expected to be
    small enough that a Query on the UserID key with a FilterExpression is acceptable.
    Revisit with a dedicated GSI if this becomes a hot path.

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        invoice_id: The "original" invoice's ID to find duplicates of

    Returns:
        List of invoice IDs that are marked as duplicates of invoice_id
    """
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key('UserID').eq(user_id),
            FilterExpression=Attr('duplicate_of_invoice_id').eq(invoice_id),
            ProjectionExpression="InvoiceID"
        )
        return [item['InvoiceID'] for item in response.get('Items', [])]
    except Exception as e:
        raise DatabaseError(f"Error getting linked duplicates for invoice '{invoice_id}'") from e


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


def get_retail_invoice_counts(dynamodb_table, user_id: str, exclude_sources=None) -> Dict[str, int]:
    """
    Get counts of retail invoices for all sub-types for a given user, optionally excluding
    given discovery_source values. Also excludes is_duplicate rows, consistent with the list
    endpoints.

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        exclude_sources: Optional list of discovery_source values to exclude from counts

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
            FilterExpression=_build_retail_list_filter(exclude_sources),
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


def get_retail_invoice_for_user(table, user_id: str, invoice_id: str) -> Dict:
    """
    Fetch a single retail invoice from the RetailInvoices base table, validating that it
    belongs to the given user.

    Shared ownership-check helper used by delete, recategorize, and mark-duplicate retail
    invoice Lambdas so this query isn't duplicated in each one.

    Args:
        table: DynamoDB table resource for RetailInvoices
        user_id: Authenticated user ID
        invoice_id: Invoice ID to fetch

    Returns:
        Invoice item dictionary

    Raises:
        NoInvoiceFoundError: If invoice not found or user doesn't own it
        DatabaseError: If database error occurs
    """
    try:
        response = table.query(
            KeyConditionExpression=Key('UserID').eq(user_id) & Key('InvoiceID').eq(invoice_id)
        )
        invoices = response.get('Items', [])

        if len(invoices) == 0:
            logging.warning(f"No invoice found for user '{user_id}' and invoice '{invoice_id}'")
            raise NoInvoiceFoundError("Invoice not found or access denied")

        return invoices[0]
    except NoInvoiceFoundError:
        raise
    except ClientError as e:
        raise DatabaseError("Error validating invoice ownership") from e


def compute_vendor_order_key(vendor_name: str, order_id: str, invoice_date: str, sub_type: str,
                              discovery_source: str):
    """
    Compute the dedup key used on the vendor-order-index GSI. Keys on (sub_type, order_id)
    when available - vendor_name is excluded since it's inconsistent across a vendor's own
    emails for one order (e.g. "Amazon" vs "Amazon.se"); falls back to (vendor, day) otherwise.
    Both branches are prefixed with discovery_source so dedup never merges across pipelines.
    Returns None if neither order_id nor invoice_date is available.
    """
    if order_id:
        return f"{discovery_source}_{sub_type}_{order_id}"
    if invoice_date:
        return f"{discovery_source}_{vendor_name}_{invoice_date[:10]}"
    return None


def find_existing_invoice(retail_invoices_table, user_id: str, vendor_order_key):
    """
    Query the vendor-order-index GSI for an existing invoice with the same vendor_order_key
    (see compute_vendor_order_key for how that key is derived). Returns None if no key could
    be computed, or no match is found.

    Known limitation: pre-existing RetailInvoices rows (written before this GSI existed)
    have no vendor_order_key attribute and are absent from this sparse index - they won't
    be found here. Accepted for the parallel-run/testing period.
    """
    if not vendor_order_key:
        return None

    try:
        response = retail_invoices_table.query(
            IndexName='vendor-order-index',
            KeyConditionExpression=Key('UserID').eq(user_id) & Key('vendor_order_key').eq(vendor_order_key)
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except ClientError as e:
        raise DatabaseError(f"Error querying vendor-order-index for {user_id}/{vendor_order_key}") from e


def resolve_duplicate(existing: Dict, new_invoice_date: str) -> str:
    """
    Decide what to do when a (UserID, vendor, order_id) match already exists.

    Default policy (per the design doc): keep the lifecycle email with the latest date -
    an earlier email for the same order is treated as superseded and overwritten in place.
    The fuzzy-match fallback for when order_id can't be resolved is deliberately out of
    scope here - exact-match only for this implementation.

    Returns:
        'update' - overwrite the existing row with the new data
        'skip'    - new data is not newer, discard it as a duplicate
    """
    existing_date = existing.get('invoice_date', '')
    if new_invoice_date and new_invoice_date > existing_date:
        return 'update'
    return 'skip'


def upsert_retail_invoice_to_dynamodb(retail_invoices_table, detail_tables: Dict, invoice_data: Dict,
                                       user_id: str, sub_type: str, s3_path: str, fallback_date: str,
                                       discovery_source: str) -> Tuple[str, str]:
    """
    Insert or upsert parsed retail invoice data into DynamoDB tables.

    Shared by parse_retail_invoice (ingestion) and recategorize_retail_invoice (re-parse on
    category change), so both pipelines write through the same path.

    Args:
        retail_invoices_table: DynamoDB table resource for RetailInvoices
        detail_tables: Dict mapping sub_type -> DynamoDB table resource for that detail table
        invoice_data: Parsed invoice data from Gemini
        user_id: User ID
        sub_type: Retail invoice sub-type
        s3_path: S3 path to the original HTML file
        fallback_date: S3 object's last-modified date, used when invoice_date can't be determined
        discovery_source: 'sweep' or 'vendor_config' - which pipeline discovered this email,
                           recorded on every write so the two pipelines' output stays queryable
                           during the parallel-run comparison period.

    Returns:
        Tuple of (invoice_id, outcome) where outcome is 'inserted', 'updated', or 'duplicate_skipped'
    """
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        vendor_name = invoice_data.get('vendor_name')
        order_id = invoice_data.get('order_id')

        # Use fallback date if invoice_date is missing or None
        invoice_date = invoice_data.get('invoice_date')
        if not invoice_date:
            # try to get the date from S3 path
            try:
                if s3_path.find("/") < 0:
                    raise ValueError
                filename = s3_path.split('/')[-1]       # get filename
                filename_date = filename.split("_")[-2]     # get date (sandwiched between vendor name and hash)
                datetime.strptime(filename_date, '%Y-%m-%d')    # validate date structure
                invoice_date = filename_date
                logging.info(f"Using date from S3 path: {filename_date}")
            except (ValueError, IndexError):
                invoice_date = fallback_date
                logging.info(f"Using S3 last-modified date as fallback for invoice_date: {fallback_date}")
        else:
            logging.info(f"Using parsed invoice_date: {invoice_date}")

        vendor_order_key = compute_vendor_order_key(vendor_name, order_id, invoice_date, sub_type, discovery_source)
        existing_invoice = find_existing_invoice(retail_invoices_table, user_id, vendor_order_key)

        if existing_invoice:
            decision = resolve_duplicate(existing_invoice, invoice_date)
            if decision == 'skip':
                logging.info(f"Duplicate detected for {user_id}/{vendor_order_key} - skipping")
                return existing_invoice['InvoiceID'], 'duplicate_skipped'
            invoice_id = existing_invoice['InvoiceID']
            logging.info(f"Updating existing invoice {invoice_id} for {user_id}/{vendor_order_key}")
        else:
            invoice_id = f"retail_invoice_{uuid4()}"

        # Prepare base retail invoice data
        base_invoice_data = {
            'UserID': user_id,
            'InvoiceID': invoice_id,
            'vendor_name': vendor_name,
            'sub_type': sub_type,
            'total_amount': invoice_data.get('total_amount'),
            'currency': invoice_data.get('currency'),
            'invoice_date': invoice_date,
            'created_at': created_at,
            's3_path': s3_path,
            'order_id': order_id,
            'payment_status': 'completed',  # Default status
            'UserID_SubType': f"{user_id}_{sub_type}",  # For GSI-2
            'discovery_source': discovery_source,
        }
        if vendor_order_key:
            base_invoice_data['vendor_order_key'] = vendor_order_key

        # Insert/overwrite RetailInvoices base table row
        logging.info(f"Writing base invoice data into RetailInvoices")
        retail_invoices_table.put_item(Item=base_invoice_data)

        # Prepare detail table data (exclude base fields)
        detail_data = invoice_data.copy()
        detail_data['InvoiceID'] = invoice_id

        # Remove base fields from detail data to avoid duplication
        base_fields = ['vendor_name', 'total_amount', 'currency', 'invoice_date', 'order_id']
        for field in base_fields:
            detail_data.pop(field, None)

        # Insert/overwrite appropriate detail table row
        detail_table = detail_tables.get(sub_type)
        if detail_table:
            logging.info(f"Writing detail data into {detail_table.table_name}")
            detail_table.put_item(Item=detail_data)
        else:
            logging.warning(f"No detail table found for sub_type: {sub_type}")

        outcome = 'updated' if existing_invoice else 'inserted'
        logging.info(f"Successfully {outcome} retail invoice with ID: {invoice_id}")
        return invoice_id, outcome

    except DatabaseError:
        raise
    except Exception as e:
        logging.error(f"Failed to upsert retail invoice into DynamoDB: {e}")
        raise DatabaseError(f"Failed to upsert retail invoice: {str(e)}") from e


def get_retail_invoice_count_by_subtype(dynamodb_table, user_id: str, sub_type: str,
                                         exclude_sources=None) -> Dict[str, int]:
    """
    Get count of retail invoices for a specific sub-type for a given user, optionally excluding
    given discovery_source values. Also excludes is_duplicate rows, consistent with the list
    endpoints. Filtering requires abandoning the pure Select='COUNT' optimization.

    Args:
        dynamodb_table: DynamoDB table resource for RetailInvoices
        user_id: User ID
        sub_type: Invoice sub-type (e.g., 'food-delivery', 'technology')
        exclude_sources: Optional list of discovery_source values to exclude from the count

    Returns:
        Dictionary with single sub-type count: {'food-delivery': 5}
    """
    try:
        # Use GSI-2: sub_type-invoice_date-index for efficient filtering
        user_id_subtype = f"{user_id}_{sub_type}"

        response = dynamodb_table.query(
            IndexName='sub_type-invoice_date-index',
            KeyConditionExpression=Key('UserID_SubType').eq(user_id_subtype),
            FilterExpression=_build_retail_list_filter(exclude_sources),
            Select='COUNT'  # Only return the count, not the items
        )

        count = response.get('Count', 0)
        result = {sub_type: count}

        logging.info(f"Retrieved retail invoice count for user '{user_id}' sub-type '{sub_type}': {count}")
        return result

    except Exception as e:
        raise DatabaseError(f"Error getting retail invoice count for '{user_id}' sub-type '{sub_type}'") from e
