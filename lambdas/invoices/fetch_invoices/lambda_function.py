import os
import json
import email
import boto3
import logging

from email.message import Message
from email.utils import parsedate_to_datetime
from botocore.config import Config

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.utility_functions import decode_string
from utils.jwt_utils import get_user_id_from_token
from utils.s3_utils import download_and_upload_attachment
from utils.dynamodb_utils import is_invoice_already_parsed, get_all_invoice_dates
from utils.secretsmanager_utils import get_oauth_tokens
from utils.gmail_api_utils import create_gmail_service, search_emails, get_email_content
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, GmailAPIError, OAuthValidationError, SecretsManagerError

s3_client = boto3.client('s3')
config = Config(retries={'max_attempts': 5, 'mode': 'adaptive'})
dynamodb = boto3.resource('dynamodb', config=config)
JWT_SECRET = os.environ['JWT_SECRET']


def extract_and_upload_invoice(msg: Message, invoices_found: int, user_id: str) -> int:
    subject = decode_string(msg['subject'])
    if subject.strip().lower() == os.environ['EMAIL_SUBJECT']:
        logging.info("Retrieving information from email...")
        invoices_found = download_and_upload_attachment(
            s3_client,
            s3_bucket_name=os.environ['S3_BUCKET'],
            msg=msg,
            invoices_found=invoices_found,
            user_id=user_id
        )

    return invoices_found


def lambda_handler(event, context):
    logging.info(f"Received this event: {json.dumps(event)}")
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

        # Get OAuth tokens from Secrets Manager
        oauth_data = get_oauth_tokens(user_id, region=os.environ['REGION'])
        access_token = oauth_data['access_token']
        refresh_token = oauth_data['refresh_token']
        expires_at = oauth_data.get('expires_at')
        
        # Get Google OAuth client credentials from environment (iOS client - no secret needed)
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
        
        logging.info("Retrieved OAuth tokens")
        
        # Create Gmail API service with automatic token refresh (no client secret for iOS OAuth)
        gmail_service = create_gmail_service(user_id, access_token, refresh_token, client_id, os.environ['REGION'], client_secret=None, expires_at=expires_at)
        
        # Search for emails using Gmail API
        sender = os.environ['EMAIL_SENDER']
        subject = os.environ['EMAIL_SUBJECT']
        
        message_list = search_emails(gmail_service, sender, subject)
        
        invoices_table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
        invoices_found = 0
        invoice_dates = get_all_invoice_dates(invoices_table, user_id)
        logging.info(f"Here are the invoice dates: {dict(invoice_dates)}")
        
        # Process emails in reverse chronological order (newest first)
        for message_info in reversed(message_list):
            message_id = message_info['id']
            
            # Get email content using Gmail API
            my_msg = get_email_content(gmail_service, message_id)
            email_date = parsedate_to_datetime(my_msg['Date']) if my_msg['Date'] else None
            
            if email_date:
                logging.info(f"Email found for date: {email_date}")
                if not is_invoice_already_parsed(email_date.month, email_date.year, invoice_dates):
                    logging.info(f"Invoice doesn't exist for: {email_date.month} and {email_date.year}! Extracting and uploading...")
                    invoices_found = extract_and_upload_invoice(my_msg, invoices_found, user_id)
                else:
                    logging.info("Invoice already exists in S3!")
            else:
                logging.warning(f"Unable to parse date from this email: {my_msg}")

        if invoices_found > 0:
            logging.info(f"Ingested {invoices_found} invoices!")
            return success_response(
                message="Rental invoices ingested successfully!",
                data={
                    "invoiceCount": invoices_found
                }
            )
        else:
            logging.info(f"No rental invoices found for user {user_id}")
            return success_response(
                message="No rental invoices found for this user."
            )

    except GmailAPIError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Gmail API error", 502, e)
        
    except OAuthValidationError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "OAuth token error", 401, e)
        
    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error retrieving OAuth tokens", 502, e)

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except InvalidTokenError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_TOKEN, "Malformed Token", 401, e)

    except TokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.TOKEN_EXPIRED, "Expired token", 401, e)

    except JWTDecodingError as e:
        return log_and_generate_error_response(ErrorCode.JWT_ERROR, "Error parsing JWT token", 500, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key in request body: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)