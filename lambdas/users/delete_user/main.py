import os
import json
import boto3
import logging

from utils.decorators import require_auth
from utils.s3_utils import delete_user_folder_in_s3
from utils.dynamodb_utils import delete_user_invoices, delete_user_in_dynamodb, delete_user_retail_invoices, delete_retail_invoice_details
from utils.secretsmanager_utils import delete_email_credentials
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import SecretsManagerError, DatabaseError, S3Error


dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
s3 = boto3.client('s3')

USERS_TABLE = os.environ['USERS_TABLE']
INVOICES_TABLE = os.environ['INVOICES_TABLE']
BUCKET_NAME = os.environ['BUCKET_NAME']

# Retail invoice table names
RETAIL_INVOICES_TABLE = os.environ['RETAIL_INVOICES_TABLE']
FOOD_DELIVERY_INVOICES_TABLE = os.environ['FOOD_DELIVERY_INVOICES_TABLE']
CLOTHING_INVOICES_TABLE = os.environ['CLOTHING_INVOICES_TABLE']
TECHNOLOGY_INVOICES_TABLE = os.environ['TECHNOLOGY_INVOICES_TABLE']
SUBSCRIPTION_INVOICES_TABLE = os.environ['SUBSCRIPTION_INVOICES_TABLE']
GROCERY_INVOICES_TABLE = os.environ['GROCERY_INVOICES_TABLE']
MISC_UTILITY_INVOICES_TABLE = os.environ['MISC_UTILITY_INVOICES_TABLE']
MISC_INVOICES_TABLE = os.environ['MISC_INVOICES_TABLE']

users_table = dynamodb.Table(USERS_TABLE)
invoices_table = dynamodb.Table(INVOICES_TABLE)
retail_invoices_table = dynamodb.Table(RETAIL_INVOICES_TABLE)

# Create detail tables dictionary
detail_tables = {
    'FoodDeliveryInvoices': dynamodb.Table(FOOD_DELIVERY_INVOICES_TABLE),
    'ClothingInvoices': dynamodb.Table(CLOTHING_INVOICES_TABLE),
    'TechnologyInvoices': dynamodb.Table(TECHNOLOGY_INVOICES_TABLE),
    'SubscriptionInvoices': dynamodb.Table(SUBSCRIPTION_INVOICES_TABLE),
    'GroceryInvoices': dynamodb.Table(GROCERY_INVOICES_TABLE),
    'MiscUtilityInvoices': dynamodb.Table(MISC_UTILITY_INVOICES_TABLE),
    'MiscInvoices': dynamodb.Table(MISC_INVOICES_TABLE)
}


@require_auth
def lambda_handler(event, context, user_id):
    """Delete user and all associated data - requires JWT authentication"""
    try:

        # delete all rental invoices for this user in the RentalInvoices table
        delete_user_invoices(invoices_table, user_id=user_id)

        # delete all retail invoices for this user
        # First delete from RetailInvoices table and get invoice IDs
        invoice_ids = delete_user_retail_invoices(retail_invoices_table, user_id=user_id)

        # Then delete from all detail tables using the invoice IDs
        if invoice_ids:
            delete_retail_invoice_details(detail_tables, invoice_ids)

        # delete secrets for this user
        delete_email_credentials(secrets_manager, user_id=user_id)

        # delete the folder for this user in S3
        delete_user_folder_in_s3(s3, user_id=user_id, s3_bucket_name=BUCKET_NAME)

        # delete this user from the Users table
        delete_user_in_dynamodb(users_table, user_id=user_id)

        logging.info(f"All data for user '{user_id}' deleted successfully!")

        return success_response(
            message=f"All data for user {user_id} deleted successfully!"
        )

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during user deletion",
            502,
            e
        )

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error deleting Gmail credentials", 502, e)

    except S3Error as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error deleting S3 folder", 502, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)
