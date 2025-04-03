import os
import json
import email
from http.client import responses

import boto3
import imaplib
import quopri
import logging

from collections import defaultdict
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from botocore.exceptions import ClientError
from botocore.config import Config

s3_client = boto3.client('s3')
config = Config(retries={'max_attempts': 5, 'mode': 'adaptive'})
dynamodb = boto3.resource('dynamodb', config=config)
secret_client = boto3.client('secretsmanager')


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


def get_s3_path(email: str, filename: str):
    username = email.split('@')[0]
    filename = filename.replace(' ', '_')
    return f"rental-invoices/{username}/{filename}"


def invoice_exists_in_dynamodb(current_month: int, current_year: int, invoice_dates: defaultdict) -> bool:
    """
    This function checks if an invoice with the current month and year exists in the DynamoDB table
    """
    """
    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    response = table.query(
        IndexName='due_date_year-due_date_month-index',
        KeyConditionExpression=Key('due_date_year').eq(current_year) & Key('due_date_month').eq(current_month)
    )
    return len(response.get('Items', [])) > 0
    """
    return invoice_dates[current_year][current_month]


def get_all_invoice_dates() -> defaultdict:
    """
    This function get the month and year for all invoices in the DynamoDB table, and returns them as a Dict
    """
    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    response = table.scan(
        ProjectionExpression="due_date_month, due_date_year"
    )
    invoices = response['Items']
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            ProjectionExpression="due_date_month, due_date_year",
            ExcluseiveStartKey=response['LastEvaluatedKey']
        )

    invoice_dates = defaultdict(lambda: defaultdict(lambda: False))
    for invoice in invoices:
        year = invoice['due_date_year']
        month = invoice ['due_date_month']
        invoice_dates[year][month] = True
    return invoice_dates


def extract_and_upload_invoice(msg: Message, invoice_count_added: bool, invoices_found: int, user: str) -> int:
    subject = decode_string(msg['subject'])
    if subject.strip().lower() == os.environ['EMAIL_SUBJECT']:

        if not invoice_count_added:
            invoices_found += 1
            invoice_count_added = True

        logging.info("Retrieving information from email...")
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                body_string = part.get_payload()
                body = get_body_from_email(body_string)
                logging.info(body)

            if part.get_content_type() == "application/pdf":
                filename = part.get_filename()
                filename = decode_string(filename)
                if filename:
                    logging.info("Downloading " + filename + "...")
                    file_content = part.get_payload(decode=True)
                    s3_key = get_s3_path(user, filename)
                    s3_client.put_object(
                        Bucket=os.environ['S3_BUCKET'],
                        Key=s3_key,
                        Body=file_content
                    )
                    logging.info(f"{filename} uploaded to S3!")

    return invoices_found


def lambda_handler(event, context):
    
    my_creds = get_email_credentials()
    user, password, imap_url = my_creds['GMAIL_USER'], my_creds['GMAIL_PASSWORD'], my_creds["GMAIL_IMAP_URL"]
    logging.info("Retrieved credentials")

    # connect to Gmail using SSL
    my_mail = imaplib.IMAP4_SSL(imap_url)
    # log in using credentials loaded from YAML file
    my_mail.login(user, password)

    # select the Inbox to fetch messages from
    my_mail.select('Inbox')

    key = "FROM"
    value = os.environ['EMAIL_SENDER']

    # perform search in mailbox using key and value from above
    _, data = my_mail.search(None, key, value)

    # get IDs of all emails that we want to fetch
    mail_id_list = data[0].split()

    messages = []
    invoices_found = 0
    invoice_dates = get_all_invoice_dates()
    logging.info(f"Here are the invoice dates: {dict(invoice_dates)}")
    for num in mail_id_list:
        _, mail_data = my_mail.fetch(num, '(RFC822)')
        messages.append(mail_data)

    for msg in messages[::-1]:
        invoice_count_added = False
        for response_part in msg:
            if type(response_part) is tuple:
                my_msg = email.message_from_bytes((response_part[1]))
                email_date = parsedate_to_datetime(my_msg['Date']) if my_msg['Date'] else None

                if email_date:
                    logging.info(f"Email found for date: {email_date}")
                    if not invoice_exists_in_dynamodb(email_date.month, email_date.year, invoice_dates):
                        logging.info(f"Invoice doesn't exist for: {email_date.month} and {email_date.year}! Extracting and uploading...")
                        invoices_found = extract_and_upload_invoice(
                            my_msg,
                            invoice_count_added,
                            invoices_found,
                            user
                        )
                    else:
                        logging.info("Invoice already exists in S3!")
                else:
                    logging.warning(f"Unable to parse date from this email: {my_msg}")

    my_mail.close()
    my_mail.logout()

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Emails identified, parsed, and uploaded!',
            'invoiceCount': invoices_found
        })
    }