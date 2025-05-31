import os
import json
import email
import boto3
import imaplib
import logging

from email.message import Message
from email.utils import parsedate_to_datetime
from botocore.config import Config

from utils.error_handling import log_and_generate_error_response
from utils.utility_functions import decode_string, get_user_id_from_token
from utils.s3_utils import download_and_upload_attachment
from utils.dynamodb_utils import is_invoice_already_parsed, get_all_invoice_dates
from utils.secretsmanager_utils import get_email_credentials
from utils.exceptions import JWTDecodingError, InvalidCredentialsError, InvalidTokenError, TokenExpiredError

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

        my_creds = get_email_credentials(user_id, region=os.environ['REGION'])

        user_email, password, imap_url = my_creds['GMAIL_USER'], my_creds['GMAIL_PASSWORD'], my_creds["GMAIL_IMAP_URL"]
        logging.info("Retrieved credentials")

        # connect to Gmail using SSL
        my_mail = imaplib.IMAP4_SSL(imap_url)
        # log in using credentials loaded from YAML file
        my_mail.login(user_email, password)

        # select the Inbox to fetch messages from
        my_mail.select('Inbox')

        key = "FROM"
        value = os.environ['EMAIL_SENDER']

        # perform search in mailbox using key and value from above
        _, data = my_mail.search(None, key, value)

        # get IDs of all emails that we want to fetch
        mail_id_list = data[0].split()

        invoices_table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
        messages = []
        invoices_found = 0
        invoice_dates = get_all_invoice_dates(invoices_table, user_id)
        logging.info(f"Here are the invoice dates: {dict(invoice_dates)}")
        for num in mail_id_list:
            _, mail_data = my_mail.fetch(num, '(RFC822)')
            messages.append(mail_data)

        for msg in messages[::-1]:
            for response_part in msg:
                if type(response_part) is tuple:
                    my_msg = email.message_from_bytes((response_part[1]))
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

        my_mail.close()
        my_mail.logout()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'{invoices_found} invoices identified, parsed, and uploaded!',
                'invoiceCount': invoices_found
            })
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