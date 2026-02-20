import os
import json
import boto3
import logging
from datetime import datetime

from utils.decorators import require_auth
from utils.dynamodb_utils import invoice_exists_in_dynamodb
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import get_oauth_tokens
from utils.s3_utils import download_and_upload_attachment
from utils.gmail_api_utils import create_gmail_service, get_latest_email_by_date
from utils.exceptions import GmailAPIError, OAuthValidationError, SecretsManagerError

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Main entry point - routes between EventBridge and API Gateway triggers"""
    try:
        # Debug: Log the incoming event structure
        logging.info(f"Received event: {json.dumps(event)}")

        # Detect trigger source - EventBridge vs API Gateway
        if 'source' in event and event['source'] == 'aws.events':
            # EventBridge trigger - process all users
            logging.info("EventBridge trigger detected - processing all users")
            return process_daily_rental_all_users()
        else:
            # API Gateway trigger - process single user
            logging.info("API Gateway trigger detected - processing single user")
            return _handle_api_gateway_request(event, context)

    except GmailAPIError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Gmail API error", 502, e)

    except OAuthValidationError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "OAuth token error", 401, e)

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error retrieving OAuth tokens", 502, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key in request body: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)


@require_auth
def _handle_api_gateway_request(event, context, user_id):
    """Handle authenticated API Gateway requests"""
    return process_daily_rental_single_user(user_id)


def process_daily_rental_single_user(user_id: str):
    invoices_table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

    current_date = datetime.utcnow()
    current_year = current_date.year
    current_month = current_date.month

    if not invoice_exists_in_dynamodb(invoices_table, user_id, current_month, current_year):
        # Get OAuth tokens from Secrets Manager
        logging.info(f"No invoice found for {current_month}/{current_year}")
        oauth_data = get_oauth_tokens(user_id, region=os.environ['REGION'])
        access_token = oauth_data['access_token']
        refresh_token = oauth_data['refresh_token']
        expires_at = oauth_data.get('expires_at')

        # Get Google OAuth client credentials (iOS client - no secret needed)
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
        logging.info("Retrieved OAuth tokens")

        # Create Gmail API service with automatic token refresh (no client secret for iOS OAuth)
        gmail_service = create_gmail_service(user_id, access_token, refresh_token, client_id, os.environ['REGION'], client_secret=None, expires_at=expires_at)

        # Get latest invoice email using Gmail API
        sender = os.environ['EMAIL_SENDER']
        subject = os.environ['EMAIL_SUBJECT']

        invoice_email = get_latest_email_by_date(gmail_service, sender, subject, current_month, current_year)
        if not invoice_email:
            logging.info(f"Invoice for {current_month}/{current_year} not found in inbox!")
            return success_response(
                message=f"Rental invoice for {current_month}/{current_year} has not been dispatched yet.",
                status_code=204
            )
        else:
            logging.info(f"Invoice for {current_month}/{current_year} found in inbox! Downloading...")
            download_and_upload_attachment(
                s3_client,
                s3_bucket_name=os.environ['S3_BUCKET'],
                msg=invoice_email,
                invoices_found=0,
                user_id=user_id
            )
            return success_response(
                message=f"Invoice for {current_month}/{current_year} found and ingested successfully!",
                status_code=201
            )
    else:
        logging.info(f"Invoice for {current_month}/{current_year} already exists. Exiting.")
        return success_response(
            message=f"Invoice for {current_month}/{current_year} has already been processed."
        )


def process_daily_rental_all_users():
    """
    Process daily rental invoice check for all users (EventBridge trigger)
    """
    try:
        users_table = dynamodb.Table(os.environ['USERS_TABLE'])
        invoices_table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

        # Scan all users (consider pagination for large user bases)
        response = users_table.scan()
        users = response['Items']

        results = {
            'total_users': len(users),
            'successful': 0,
            'failed': 0,
            'errors': [],
            'processed_users': []
        }

        current_date = datetime.utcnow()
        current_year = current_date.year
        current_month = current_date.month

        for user in users:
            user_id = user['UserID']
            try:
                logging.info(f"Processing daily rental check for user: {user_id}")

                # Check if invoice already exists for this user
                if not invoice_exists_in_dynamodb(invoices_table, user_id, current_month, current_year):
                    # Process this user (similar to single user logic)
                    oauth_data = get_oauth_tokens(user_id, region=os.environ['REGION'])
                    access_token = oauth_data['access_token']
                    refresh_token = oauth_data['refresh_token']
                    expires_at = oauth_data.get('expires_at')

                    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
                    gmail_service = create_gmail_service(user_id, access_token, refresh_token, client_id, os.environ['REGION'], client_secret=None, expires_at=expires_at)

                    sender = os.environ['EMAIL_SENDER']
                    subject = os.environ['EMAIL_SUBJECT']

                    invoice_email = get_latest_email_by_date(gmail_service, sender, subject, current_month, current_year)
                    if invoice_email:
                        download_and_upload_attachment(
                            s3_client,
                            s3_bucket_name=os.environ['S3_BUCKET'],
                            msg=invoice_email,
                            invoices_found=0,
                            user_id=user_id
                        )
                        results['processed_users'].append(f"{user_id}: Invoice found and processed")
                    else:
                        results['processed_users'].append(f"{user_id}: No invoice found for {current_month}/{current_year}")
                else:
                    results['processed_users'].append(f"{user_id}: Invoice already exists")

                results['successful'] += 1

            except Exception as e:
                error_msg = f"User {user_id}: {str(e)}"
                results['failed'] += 1
                results['errors'].append(error_msg)
                logging.error(error_msg)

        logging.info(f"Daily rental check completed: {results['successful']} successful, {results['failed']} failed")
        return success_response(
            message="Daily rental invoice check completed for all users",
            data=results
        )

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Error processing daily rental check for all users", 500, e)