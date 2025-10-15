import os
import json
import boto3
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from utils.jwt_utils import get_user_id_from_token
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import get_oauth_tokens
from utils.dynamodb_utils import fetch_user_by_id, get_active_vendors, update_last_retail_invoice_fetch
from utils.gmail_api_utils import create_gmail_service, build_gmail_query, get_email_content, extract_html_from_email
from utils.s3_utils import generate_retail_invoice_s3_key, s3_file_exists, upload_html_to_s3
from utils.exceptions import (
    JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError,
    GmailAPIError, OAuthValidationError, SecretsManagerError, RefreshTokenExpiredError,
    UserNotFoundError, DatabaseError
)

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
JWT_SECRET = os.environ['JWT_SECRET']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def determine_search_date_range(user: dict, custom_start_date: str = None, custom_end_date: str = None) -> tuple:
    """
    Determine the date range for fetching retail invoices based on last fetch timestamp or custom dates

    Args:
        user: User dict from DynamoDB
        custom_start_date: Optional custom start date in "YYYY-MM-DD" format
        custom_end_date: Optional custom end date in "YYYY-MM-DD" format

    Returns:
        Tuple of (start_date, end_date) in Gmail format "YYYY/MM/DD"
    """
    # If custom dates are provided, use them
    if custom_start_date and custom_end_date:
        try:
            # Validate and convert format from YYYY-MM-DD to YYYY/MM/DD
            start_dt = datetime.strptime(custom_start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(custom_end_date, "%Y-%m-%d")

            start_date = start_dt.strftime("%Y/%m/%d")
            end_date = end_dt.strftime("%Y/%m/%d")

            logger.info(f"Using custom date range: {start_date} to {end_date}")
            return start_date, end_date
        except ValueError as e:
            logger.error(f"Invalid custom date format: {e}. Expected YYYY-MM-DD")
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD. Error: {e}")

    # Otherwise, use automatic logic based on last fetch
    last_fetch = user.get('last_retail_invoice_fetch')

    end_date = datetime.utcnow().strftime("%Y/%m/%d")

    if last_fetch:
        # Incremental fetch from last fetch date
        logger.info(f"Last retail invoice fetch: {last_fetch}")
        try:
            # Parse ISO 8601 timestamp and convert to Gmail date format
            last_fetch_dt = datetime.fromisoformat(last_fetch.replace('Z', '+00:00'))
            start_date = last_fetch_dt.strftime("%Y/%m/%d")
            logger.info(f"Incremental fetch from {start_date} to {end_date}")
        except ValueError as e:
            logger.warning(f"Invalid last_fetch timestamp format: {last_fetch}. Using default 30 days. Error: {e}")
            start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y/%m/%d")
    else:
        # First-time fetch: last 30 days
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y/%m/%d")
        logger.info(f"First-time fetch (last 30 days): {start_date} to {end_date}")

    return start_date, end_date


def process_vendor_emails(gmail_service, vendor: dict, user_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Process emails for a single vendor

    Args:
        gmail_service: Gmail API service object
        vendor: Vendor configuration dict
        user_id: User ID
        start_date: Start date for search (YYYY/MM/DD)
        end_date: End date for search (YYYY/MM/DD)

    Returns:
        Dict with vendor_id, emails_found, and errors
    """
    vendor_id = vendor['vendor_id']
    sub_type = vendor['invoice_sub_type']

    logger.info(f"Processing vendor: {vendor_id} (category: {sub_type})")

    result = {
        'vendor_id': vendor_id,
        'emails_found': 0,
        'errors': []
    }

    try:
        # Build Gmail query from vendor config
        email_patterns = vendor.get('default_email_patterns', [])
        subject_keywords = vendor.get('default_subject_keywords', [])

        if not email_patterns:
            logger.warning(f"No email patterns configured for vendor {vendor_id}, skipping")
            return result

        query = build_gmail_query(email_patterns, subject_keywords, start_date, end_date)

        # Search Gmail
        search_response = gmail_service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100  # Cap at 100 per vendor to stay within timeout
        ).execute()

        messages = search_response.get('messages', [])
        logger.info(f"Found {len(messages)} emails for {vendor_id}")

        # Process each email
        for msg_info in messages:
            try:
                message_id = msg_info['id']

                # Get full email content
                email_content = get_email_content(gmail_service, message_id)

                # Extract date
                from email.utils import parsedate_to_datetime
                email_date_str = email_content.get('Date')
                if not email_date_str:
                    logger.warning(f"No date found in email {message_id}, skipping")
                    continue

                email_date = parsedate_to_datetime(email_date_str)

                # Generate S3 key
                s3_key = generate_retail_invoice_s3_key(
                    user_id=user_id,
                    vendor_id=vendor_id,
                    sub_type=sub_type,
                    email_date=email_date,
                    message_id=message_id
                )

                # Check if already exists (skip duplicates to avoid triggering parser)
                if s3_file_exists(s3_client, os.environ['S3_BUCKET'], s3_key):
                    logger.info(f"Skipping duplicate: {s3_key}")
                    continue

                # Extract HTML
                html_content = extract_html_from_email(email_content)

                if not html_content:
                    logger.warning(f"No HTML content found for message {message_id}")
                    continue

                # Upload to S3
                upload_html_to_s3(s3_client, os.environ['S3_BUCKET'], s3_key, html_content)

                result['emails_found'] += 1

                # Rate limiting (avoid Gmail API throttling)
                time.sleep(0.1)

            except Exception as email_error:
                logger.error(f"Error processing email {message_id} for {vendor_id}: {email_error}")
                result['errors'].append({
                    'message_id': message_id,
                    'error': str(email_error)
                })
                continue

        logger.info(f"Processed {result['emails_found']} new emails for {vendor_id}")

        # Rate limiting between vendors
        time.sleep(0.2)

    except Exception as vendor_error:
        logger.error(f"Error processing vendor {vendor_id}: {vendor_error}")
        result['errors'].append({
            'error': str(vendor_error)
        })

    return result


def lambda_handler(event, context):
    """
    Fetch retail invoices from Gmail for all active vendors

    API Endpoint: POST /v1/invoices/retail/ingest

    Request Body (optional):
    {
        "start_date": "2025-01-01",  # Optional: YYYY-MM-DD format
        "end_date": "2025-10-15"     # Optional: YYYY-MM-DD format
    }

    Response:
    {
        "message": "Retail invoices fetched successfully",
        "data": {
            "totalEmailsFound": 15,
            "byVendor": {
                "dominos": 3,
                "foodora": 5,
                ...
            },
            "dateRange": {
                "start": "2025/09/06",
                "end": "2025/10/06"
            },
            "errors": []
        }
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Authenticate user
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)

        # Get user info (including last_retail_invoice_fetch field)
        users_table = dynamodb.Table(os.environ['USERS_TABLE'])
        user = fetch_user_by_id(users_table, user_id)

        # Parse optional request body for custom date range
        custom_start_date = None
        custom_end_date = None

        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            custom_start_date = body.get('start_date')
            custom_end_date = body.get('end_date')

            # Validate: both dates must be provided if using custom range
            if (custom_start_date and not custom_end_date) or (custom_end_date and not custom_start_date):
                return log_and_generate_error_response(
                    ErrorCode.MISSING_FIELDS,
                    "Both start_date and end_date must be provided for custom date range",
                    400,
                    ValueError("Incomplete date range")
                )

        # Determine search date range
        start_date, end_date = determine_search_date_range(user, custom_start_date, custom_end_date)

        # Load active vendors from VendorConfig
        vendor_config_table = dynamodb.Table(os.environ['VENDOR_CONFIG_TABLE'])
        vendors = get_active_vendors(vendor_config_table)

        if not vendors:
            logger.info("No active vendors found in VendorConfig")
            return success_response(
                message="No active vendors configured for retail invoice fetching",
                data={
                    'totalEmailsFound': 0,
                    'byVendor': {},
                    'dateRange': {'start': start_date, 'end': end_date}
                }
            )

        # Get OAuth tokens
        oauth_data = get_oauth_tokens(user_id, region=os.environ['REGION'])
        access_token = oauth_data['access_token']
        refresh_token = oauth_data['refresh_token']
        expires_at = oauth_data.get('expires_at')

        logger.info("Retrieved OAuth tokens")

        # Create Gmail API service
        gmail_service = create_gmail_service(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
            region=os.environ['REGION'],
            client_secret=None,
            expires_at=expires_at
        )

        # Process each vendor
        results = {
            'total_emails': 0,
            'by_vendor': {},
            'all_errors': []
        }

        for vendor in vendors:
            vendor_result = process_vendor_emails(
                gmail_service=gmail_service,
                vendor=vendor,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )

            vendor_id = vendor_result['vendor_id']
            emails_found = vendor_result['emails_found']

            results['total_emails'] += emails_found
            results['by_vendor'][vendor_id] = emails_found

            if vendor_result['errors']:
                results['all_errors'].extend(vendor_result['errors'])

        # Update last_retail_invoice_fetch timestamp
        update_last_retail_invoice_fetch(users_table, user_id)

        logger.info(f"Fetch complete: {results['total_emails']} total emails across {len(vendors)} vendors")

        return success_response(
            message="Retail invoices fetched successfully",
            data={
                'totalEmailsFound': results['total_emails'],
                'byVendor': results['by_vendor'],
                'dateRange': {
                    'start': start_date,
                    'end': end_date
                },
                'errors': results['all_errors'][:20]  # Cap errors in response
            }
        )

    except GmailAPIError as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Gmail API error", 502, e)

    except RefreshTokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.GMAIL_TOKEN_EXPIRED, "Gmail account needs to be re-connected", 502, e)

    except OAuthValidationError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "OAuth token error", 401, e)

    except SecretsManagerError as e:
        return log_and_generate_error_response(ErrorCode.GMAIL_TOKEN_EXPIRED, "Error retrieving OAuth tokens", 502, e)

    except InvalidCredentialsError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_CREDENTIALS, "Invalid Credentials", 401, e)

    except InvalidTokenError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_TOKEN, "Malformed Token", 401, e)

    except TokenExpiredError as e:
        return log_and_generate_error_response(ErrorCode.TOKEN_EXPIRED, "Expired token", 401, e)

    except JWTDecodingError as e:
        return log_and_generate_error_response(ErrorCode.JWT_ERROR, "Error parsing JWT token", 500, e)

    except UserNotFoundError as e:
        return log_and_generate_error_response(ErrorCode.USER_NOT_FOUND, "User not found", 404, e)

    except DatabaseError as e:
        return log_and_generate_error_response(ErrorCode.DATABASE_ERROR, "Database error", 500, e)

    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key in request body: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)