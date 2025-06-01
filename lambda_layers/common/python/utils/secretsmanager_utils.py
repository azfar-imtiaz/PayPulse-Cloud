import json
import boto3
import logging
from typing import Dict
from botocore.exceptions import ClientError

from utils.exceptions import SecretsManagerError


def store_email_credentials(secrets_manager, user_id: str, email: str, gmail_app_password: str):
    secret_name = f"gmail/user/{user_id}"
    try:
        secret_value = json.dumps({
            "GMAIL_USER": email,
            "GMAIL_PASSWORD": gmail_app_password,
            "GMAIL_IMAP_URL": "imap.gmail.com"
        })
        secrets_manager.create_secret(
            Name=secret_name,
            SecretString=secret_value
        )
        logging.info(f"User secret for {user_id} stored successfully.")
    except Exception as e:
        logging.error(f"Error creating secret '{secret_name}': {e}")
        raise SecretsManagerError(f"Error creating secret for user {user_id}") from e


def get_email_credentials(user_id: str, region: str) -> Dict:
    secret_name = f"gmail/user/{user_id}"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


