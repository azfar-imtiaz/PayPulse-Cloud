import logging

from utils.exceptions import S3Error


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
