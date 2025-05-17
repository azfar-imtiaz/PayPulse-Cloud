import logging
from email.message import Message

from botocore.exceptions import ClientError
from utils.exceptions import S3Error
from utils.utility_functions import get_body_from_email, decode_string


def create_user_folder_in_s3(s3, user_id: str, s3_bucket_name: str):
    key = f"rental-invoices/{user_id}/"
    try:
        s3.put_object(
            Bucket=s3_bucket_name,
            Key=key
        )
        logging.info(f"Folder for '{user_id}' created successfully in S3.")
    except Exception as e:
        logging.error(f"Error creating S3 folder '{key}' for user '{user_id}': {e}")
        raise S3Error(f"Error creating S3 folder for user {user_id}") from e


def get_s3_path_to_rental_invoices(user_id: str, filename: str) -> str:
    filename = filename.replace(' ', '_')
    return f"rental-invoices/{user_id}/{filename}"


def download_file_from_s3(s3_client, bucket_name: str, s3_key: str) -> str:
    """
    This function downloads a file from an S3 bucket to the local Lambda environment storage
    """
    # download the file to /tmp
    filename = f"/tmp/{s3_key.split('/')[-1]}"
    try:
        s3_client.download_file(bucket_name, s3_key, filename)
        return filename
    except ClientError as e:
        raise S3Error(f"{filename} could not be downloaded.") from e


def download_and_upload_attachment(s3_client, s3_bucket_name: str, msg: Message, invoices_found: int, user_id: str):
    """
    This function is used to download a PDF attachment from an email to the appropriate path in the S3 bucket
    """
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
                s3_key = get_s3_path_to_rental_invoices(user_id, filename)
                s3_client.put_object(
                    Bucket=s3_bucket_name,
                    Key=s3_key,
                    Body=file_content
                )
                invoices_found += 1
                logging.info(f"rental-invoices/{user_id}/{filename} uploaded to S3!")
    return invoices_found