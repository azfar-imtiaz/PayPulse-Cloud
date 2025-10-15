import logging
from email.message import Message

from botocore.exceptions import ClientError
from utils.exceptions import S3Error
from utils.utility_functions import get_body_from_email, decode_string


def create_user_folders_in_s3(s3, user_id: str, s3_bucket_name: str):
    """Create the complete folder structure for a user"""
    folders = [
        f"invoices/{user_id}/rental/",
        f"invoices/{user_id}/retail/food-delivery/",
        f"invoices/{user_id}/retail/clothing/",
        f"invoices/{user_id}/retail/technology/",
        f"invoices/{user_id}/retail/subscriptions/",
        f"invoices/{user_id}/retail/grocery/",
        f"invoices/{user_id}/retail/utility/",
        f"invoices/{user_id}/retail/miscellaneous/"
    ]

    try:
        for key in folders:
            s3.put_object(
                Bucket=s3_bucket_name,
                Key=key
            )
        logging.info(f"Complete folder structure for '{user_id}' created successfully in S3.")
    except Exception as e:
        raise S3Error(f"Error creating S3 folder structure for user '{user_id}'") from e


def delete_user_folder_in_s3(s3, user_id: str, s3_bucket_name: str):
    try:
        prefix = f"invoices/{user_id}/"
        response = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix=prefix)
        objects_deleted_count = 0
        for obj in response.get('Contents', []):
            s3.delete_object(Bucket=s3_bucket_name, Key=obj['Key'])
            objects_deleted_count += 1
        logging.info(f"{objects_deleted_count} objects deleted from S3!")
    except Exception as e:
        raise S3Error(f"Error deleting user folder for {user_id}") from e


def get_s3_path_to_rental_invoices(user_id: str, filename: str) -> str:
    """Get S3 path for rental invoices (backward compatibility)"""
    filename = filename.replace(' ', '_')
    return f"invoices/{user_id}/rental/{filename}"


def get_s3_path_to_invoice(user_id: str, invoice_type: str, filename: str, retail_category: str = None) -> str:
    """Get S3 path for any type of invoice

    Args:
        user_id: User identifier
        invoice_type: 'rental' or 'retail'
        filename: Invoice filename
        retail_category: Required for retail invoices (see get_valid_retail_categories())
    """
    filename = filename.replace(' ', '_')

    if invoice_type == 'rental':
        return f"invoices/{user_id}/rental/{filename}"
    elif invoice_type == 'retail':
        if not retail_category:
            raise ValueError("retail_category is required for retail invoices")
        valid_categories = get_valid_retail_categories()
        if retail_category not in valid_categories:
            raise ValueError(f"Invalid retail_category. Must be one of: {valid_categories}")
        return f"invoices/{user_id}/retail/{retail_category}/{filename}"
    else:
        raise ValueError("invoice_type must be 'rental' or 'retail'")


def get_valid_retail_categories() -> list:
    """Get list of valid retail categories (matches DynamoDB table structure)"""
    return [
        'food-delivery',
        'clothing',
        'technology',
        'subscriptions',
        'grocery',
        'utility',
        'miscellaneous'
    ]


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
                logging.info(f"{s3_key} uploaded to S3!")
    return invoices_found


def generate_retail_invoice_s3_key(user_id: str, vendor_id: str, sub_type: str,
                                    email_date: str, message_id: str) -> str:
    """
    Generate S3 key for retail invoice HTML

    Args:
        user_id: User ID
        vendor_id: Vendor ID (e.g., "dominos")
        sub_type: Invoice sub-type (e.g., "food-delivery")
        email_date: Email date as datetime object or ISO string
        message_id: Gmail message ID

    Returns:
        S3 key path

    Example:
        "invoices/user_123/retail/food-delivery/dominos_2025-10-06_a3f9c2e1.html"
    """
    import hashlib
    from datetime import datetime

    # Convert email_date to string if it's datetime
    if isinstance(email_date, datetime):
        date_str = email_date.strftime("%Y-%m-%d")
    else:
        # Assume it's already a string in ISO format
        date_str = email_date[:10]  # Extract YYYY-MM-DD

    # Use first 8 chars of message_id hash for uniqueness
    msg_hash = hashlib.md5(message_id.encode()).hexdigest()[:8]

    filename = f"{vendor_id}_{date_str}_{msg_hash}.html"
    s3_key = f"invoices/{user_id}/retail/{sub_type}/{filename}"

    return s3_key


def s3_file_exists(s3_client, bucket_name: str, s3_key: str) -> bool:
    """
    Check if file already exists in S3

    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        s3_key: S3 object key

    Returns:
        True if file exists, False otherwise
    """
    try:
        s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        # Handle both string and integer error codes for not found
        if error_code == '404' or error_code == 404 or error_code == 'NotFound':
            return False
        # Handle 403 Forbidden - treat as file doesn't exist to allow upload attempt
        # The upload will fail with proper error if there's actually a permission issue
        if error_code == '403' or error_code == 403 or error_code == 'Forbidden':
            logging.warning(f"S3 head_object got 403 for {s3_key}, treating as non-existent")
            return False
        # Log the actual error for debugging
        logging.error(f"S3 head_object error for {s3_key}: {error_code} - {e.response['Error'].get('Message', '')}")
        raise S3Error(f"Error checking if S3 file exists: {s3_key}") from e


def upload_html_to_s3(s3_client, bucket_name: str, s3_key: str, html_content: str) -> None:
    """
    Upload HTML content to S3

    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        s3_key: S3 object key
        html_content: HTML content as string
    """
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=html_content.encode('utf-8'),
            ContentType='text/html'
        )
        logging.info(f"Uploaded to S3: {s3_key}")
    except Exception as e:
        raise S3Error(f"Error uploading HTML to S3: {s3_key}") from e