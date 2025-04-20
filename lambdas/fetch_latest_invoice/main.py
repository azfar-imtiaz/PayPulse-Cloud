import os
import json
import email
import boto3
import imaplib
import quopri
import logging
from datetime import datetime

from email.header import decode_header
from email.utils import parsedate_to_datetime
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')


def get_email_credentials():
    secret_name = os.environ['EMAIL_CREDS']
    region_name = os.environ['REGION']

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


def decode_string(s):
    decoded_bytes, charset = decode_header(s)[0]
    decoded_string = decoded_bytes.decode(charset) \
        if isinstance(decoded_bytes, bytes) else decoded_bytes
    return decoded_string


def get_body_from_email(s):
    decoded_bytes = quopri.decodestring(s)
    decoding_string = decoded_bytes.decode('utf-8')
    return decoding_string


def get_s3_path(email, filename):
    username = email.split('@')[0]
    filename = filename.replace(' ', '_')
    return f"rental-invoices/{username}/{filename}"


def invoice_exists_in_dynamodb(current_month, current_year):
    """
    This function checks if an invoice with the current month and year exists in the DynamoDB table
    """
    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    response = table.query(
        IndexName='due_date_year-due_date_month-index',
        KeyConditionExpression=Key('due_date_year').eq(current_year) & Key('due_date_month').eq(current_month)
    )
    return len(response.get('Items', [])) > 0


def fetch_latest_invoice_email(user, password, imap_url, current_month, current_year):
    
    # connect to Gmail using SSL
    my_mail = imaplib.IMAP4_SSL(imap_url)
    # log in using credentials loaded from YAML file
    my_mail.login(user, password)

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


def download_and_upload_attachment(msg, user):
    for part in msg.walk():
        if part.get_content_type() == 'text/plain':
            body_string = part.get_payload()
            body = get_body_from_email(body_string)
            logging.info(body)

        if part.get_content_type() == "application/pdf":
            filename = part.get_filename()
            filename = decode_string(filename)                                
            if filename:
                logging.info(f"Downloading {filename}...")
                file_content = part.get_payload(decode=True)
                s3_key = get_s3_path(user, filename)
                s3_client.put_object(
                    Bucket=os.environ['S3_BUCKET'],
                    Key=s3_key,
                    Body=file_content
                )
                logging.info(f"{filename} uploaded to S3!")


def lambda_handler(event, context):    
    current_date = datetime.utcnow()
    current_year = current_date.year
    current_month = current_date.month

    if invoice_exists_in_dynamodb(current_month, current_year):
        print(f"Invoice for {current_month}/{current_year} already exists. Exiting")
        return {
            "statusCode": 200,
            "body": "Invoice already processed."
        }
    
    # get credentials
    my_creds = get_email_credentials()
    user, password, imap_url = my_creds['GMAIL_USER'], my_creds['GMAIL_PASSWORD'], my_creds["GMAIL_IMAP_URL"]
    logging.info("Retrieved credentials")

    invoice_email = fetch_latest_invoice_email(user, password, imap_url, current_month, current_year)
    if not invoice_email:
        return {
            "statusCode": 200,
            "body": f"No invoice for {current_month}/{current_year} found yet."
        }

    download_and_upload_attachment(invoice_email, user)

    return {
        'statusCode': 200,
        'body': "Invoice successfully fetched and uploaded to S3 bucket."
    }