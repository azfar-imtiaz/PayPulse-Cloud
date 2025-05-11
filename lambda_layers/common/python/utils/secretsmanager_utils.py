import json
import logging

from utils.exceptions import SecretsManagerError


def store_gmail_credentials(secrets_manager, user_id: str, email: str, gmail_app_password: str):
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


