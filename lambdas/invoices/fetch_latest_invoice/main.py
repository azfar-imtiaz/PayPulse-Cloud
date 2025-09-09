import os
import json
import boto3
import logging
from datetime import datetime

from utils.dynamodb_utils import invoice_exists_in_dynamodb
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import get_oauth_tokens
from utils.s3_utils import download_and_upload_attachment
from utils.jwt_utils import get_user_id_from_token
from utils.gmail_api_utils import create_gmail_service, get_latest_email_by_date
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError, GmailAPIError, OAuthValidationError, SecretsManagerError

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
JWT_SECRET = os.environ['JWT_SECRET']


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
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