import os
import json
import email
from email.message import Message

import boto3
import imaplib
import logging
from datetime import datetime
from typing import Union
from email.utils import parsedate_to_datetime

from utils.dynamodb_utils import invoice_exists_in_dynamodb
from utils.error_handling import log_and_generate_error_response
from utils.secretsmanager_utils import get_email_credentials
from utils.s3_utils import download_and_upload_attachment
from utils.utils import get_user_id_from_token
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
JWT_SECRET = os.environ['JWT_SECRET']


def fetch_latest_invoice_email(user_email: str, password: str, imap_url: str, current_month: int, current_year: int) -> Union[None, Message]:
    
    # connect to Gmail using SSL
    my_mail = imaplib.IMAP4_SSL(imap_url)
    # log in using credentials loaded from YAML file
    my_mail.login(user_email, password)

    # select the Inbox to fetch messages from
    my_mail.select('Inbox')

    email_sender = os.environ['EMAIL_SENDER']
    email_subject = os.environ['EMAIL_SUBJECT']

    current_date = datetime(current_year, current_month, 1)
    formatted_date = current_date.strftime("%d-%b-%Y")

    search_query = f'FROM "{email_sender}" SUBJECT "{email_subject}" SINCE "{formatted_date}"'
    print(f"This is the search query: {search_query}")
    # perform search in mailbox using query from above
    status, data = my_mail.search(None, search_query)

    if status != "OK":
        print("Error searching for emails")
        return None

    email_ids = data[0].split()
    if not email_ids:
        return None

    # fetch the latest email
    latest_email_id = email_ids[-1]
    status, data = my_mail.fetch(latest_email_id, "(RFC822)")
    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    # check email date
    email_date_str = msg["Date"]
    email_date = parsedate_to_datetime(email_date_str)

    # an email with the same month and year as current month and year has been found. This means we have a new invoice
    if email_date.year == current_year and email_date.month == current_month:
        print(f"Found email from {email_sender} with subject {email_subject} from {current_month}/{current_year}")
        return msg
    else:
        print(f"No email found from {email_sender} with subject {email_subject} from {current_month}/{current_year}")
        return None


def lambda_handler(event, context):
    try:
        auth_header = event['headers'].get('Authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
        invoices_table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

        current_date = datetime.utcnow()
        current_year = current_date.year
        current_month = current_date.month

        if invoice_exists_in_dynamodb(invoices_table, user_id, current_month, current_year):
            print(f"Invoice for {current_month}/{current_year} already exists. Exiting")
            return {
                "statusCode": 200,
                "body": "Invoice already processed."
            }

        # get credentials
        my_creds = get_email_credentials(user_id, region=os.environ['REGION'])
        user_email, password, imap_url = my_creds['GMAIL_USER'], my_creds['GMAIL_PASSWORD'], my_creds["GMAIL_IMAP_URL"]
        logging.info("Retrieved credentials")

        invoice_email = fetch_latest_invoice_email(user_email, password, imap_url, current_month, current_year)
        if not invoice_email:
            return {
                "statusCode": 200,
                "body": f"No invoice for {current_month}/{current_year} found yet."
            }

        download_and_upload_attachment(
            s3_client,
            s3_bucket_name=os.environ['S3_BUCKET'],
            msg=invoice_email,
            invoices_found=0,
            user_id=user_id
        )

        return {
            'statusCode': 200,
            'body': "Invoice successfully fetched and uploaded to S3 bucket."
        }
    except InvalidCredentialsError as e:
        return log_and_generate_error_response(error_code=401, error_message="Invalid credentials", error=e)
    except InvalidTokenError as e:
        return log_and_generate_error_response(error_code=401, error_message="Invalid token", error=e)
    except TokenExpiredError as e:
        return log_and_generate_error_response(error_code=401, error_message="Expired token", error=e)
    except JWTDecodingError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error decoding JWT token", error=e)
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(error_code=400, error_message="Invalid JSON in request body", error=e)
    except KeyError as e:
        return log_and_generate_error_response(error_code=400, error_message=f"Missing key in request body: {e}", error=e)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return log_and_generate_error_response(error_code=500, error_message="Internal Server Error", error=e)