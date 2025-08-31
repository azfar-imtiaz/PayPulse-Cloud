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
        raise SecretsManagerError("Error retrieving secret") from e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


def delete_email_credentials(secrets_manager, user_id: str):
    secret_id = f"gmail/user/{user_id}"
    try:
        secrets_manager.delete_secret(
            SecretId=secret_id,
            ForceDeleteWithoutRecovery=True
        )
        logging.info(f"Secret ID {secret_id} successfully deleted!")
    except secrets_manager.exceptions.ResourceNotFoundException:
        # this means no secret was found for this user - that's okay I guess
        logging.warning(f"No secret found for {user_id}")
        pass
    except ClientError as e:
        raise SecretsManagerError(f"Error deleting secret for {user_id}") from e


def store_oauth_tokens(user_id: str, access_token: str, refresh_token: str, expires_in: int, scope: str, region: str, google_user_info: Dict[str, str] = None):
    """
    Stores OAuth tokens for a user in Secrets Manager.
    
    Args:
        user_id: The user ID
        access_token: OAuth access token
        refresh_token: OAuth refresh token  
        expires_in: Token expiration in seconds
        scope: OAuth scope granted
        region: AWS region
        google_user_info: Google user information (optional)
        
    Raises:
        SecretsManagerError: If storage fails
    """
    from utils.oauth_utils import prepare_oauth_secret_data
    
    secret_name = f"gmail/user/{user_id}"
    
    # Prepare OAuth data with Google user info
    oauth_data = prepare_oauth_secret_data(access_token, refresh_token, expires_in, scope, google_user_info)
    
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region
    )
    
    try:
        # Try to update existing secret first
        client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(oauth_data)
        )
        logging.info(f"Updated OAuth tokens for user {user_id}")
        
    except client.exceptions.ResourceNotFoundException:
        # Secret doesn't exist, create it
        try:
            client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(oauth_data)
            )
            logging.info(f"Created OAuth tokens for user {user_id}")
        except Exception as e:
            raise SecretsManagerError(f"Error creating OAuth secret for user {user_id}") from e
            
    except ClientError as e:
        raise SecretsManagerError(f"Error storing OAuth tokens for user {user_id}") from e


def get_oauth_tokens(user_id: str, region: str) -> Dict:
    """
    Retrieves OAuth tokens for a user from Secrets Manager.
    
    Args:
        user_id: The user ID
        region: AWS region
        
    Returns:
        Dictionary containing OAuth token data
        
    Raises:
        SecretsManagerError: If retrieval fails
    """
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
        raise SecretsManagerError(f"Error retrieving OAuth tokens for user {user_id}") from e
    
    secret = get_secret_value_response['SecretString']
    oauth_data = json.loads(secret)
    
    # Check if token is expired and needs refresh
    from datetime import datetime
    if 'expires_at' in oauth_data:
        expires_at = datetime.fromisoformat(oauth_data['expires_at'])
        if datetime.utcnow() >= expires_at:
            logging.warning(f"Access token for user {user_id} has expired")
            oauth_data['is_expired'] = True
    
    return oauth_data


def update_oauth_tokens(user_id: str, access_token: str, refresh_token: str, expires_in: int, region: str):
    """
    Updates existing OAuth tokens for a user in Secrets Manager (used for token refresh).
    
    Args:
        user_id: The user ID
        access_token: New OAuth access token
        refresh_token: OAuth refresh token (may be same as before)
        expires_in: Token expiration in seconds
        region: AWS region
        
    Raises:
        SecretsManagerError: If update fails
    """
    from utils.oauth_utils import prepare_oauth_secret_data
    
    secret_name = f"gmail/user/{user_id}"
    
    # Get existing OAuth data to preserve scope and Google user info
    try:
        existing_data = get_oauth_tokens(user_id, region)
        scope = existing_data.get('scope', 'https://www.googleapis.com/auth/gmail.readonly')
        # Preserve Google user information during token refresh
        google_user_info = {
            'google_user_id': existing_data.get('google_user_id', ''),
            'google_email': existing_data.get('google_email', ''),
            'google_name': existing_data.get('google_name', ''),
            'google_verified_email': existing_data.get('google_verified_email', False)
        }
    except SecretsManagerError:
        # If we can't get existing data, use defaults
        scope = 'https://www.googleapis.com/auth/gmail.readonly'
        google_user_info = None
    
    # Prepare updated OAuth data
    oauth_data = prepare_oauth_secret_data(access_token, refresh_token, expires_in, scope, google_user_info)
    
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region
    )
    
    try:
        client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(oauth_data)
        )
        logging.info(f"Successfully updated OAuth tokens for user {user_id}")
        
    except ClientError as e:
        raise SecretsManagerError(f"Error updating OAuth tokens for user {user_id}") from e
