import logging
from typing import Dict, Any
from utils.exceptions import OAuthValidationError

def validate_oauth_tokens(access_token: str, refresh_token: str, scope: str = "") -> None:
    """
    Validates OAuth tokens received from iOS app.
    
    Args:
        access_token: The OAuth access token
        refresh_token: The OAuth refresh token 
        scope: The granted scope (optional)
        
    Raises:
        OAuthValidationError: If tokens are invalid
    """
    
    if not access_token or not isinstance(access_token, str):
        raise OAuthValidationError("Invalid or missing access_token")
        
    if not refresh_token or not isinstance(refresh_token, str):
        raise OAuthValidationError("Invalid or missing refresh_token")
        
    # Basic format validation for Google OAuth tokens
    if not access_token.startswith(('ya29.', 'ya29-')):
        logging.warning("Access token doesn't match expected Google format")
        
    # Validate scope contains Gmail readonly access
    if scope and 'gmail.readonly' not in scope:
        logging.warning(f"Scope doesn't include gmail.readonly: {scope}")
        
    logging.info("OAuth token validation passed")

def prepare_oauth_secret_data(access_token: str, refresh_token: str, expires_in: int, scope: str, google_user_info: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Prepares OAuth token data for storage in Secrets Manager.
    
    Args:
        access_token: The OAuth access token
        refresh_token: The OAuth refresh token
        expires_in: Token expiration time in seconds
        scope: The granted scope
        google_user_info: Google user information (optional)
        
    Returns:
        Dictionary containing formatted OAuth data
    """
    
    import time
    from datetime import datetime, timedelta
    
    # Calculate expiration timestamp
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    oauth_data = {
        "access_token": access_token,
        "refresh_token": refresh_token, 
        "expires_at": expires_at.isoformat(),
        "expires_in": expires_in,
        "scope": scope,
        "token_type": "Bearer",
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Add Google user information if provided
    if google_user_info:
        oauth_data.update(google_user_info)
    
    return oauth_data

def is_token_expired(oauth_data: Dict[str, Any]) -> bool:
    """
    Checks if an OAuth access token is expired.
    
    Args:
        oauth_data: Dictionary containing OAuth token data
        
    Returns:
        True if token is expired, False otherwise
    """
    if 'expires_at' not in oauth_data:
        return False
        
    from datetime import datetime
    expires_at = datetime.fromisoformat(oauth_data['expires_at'])
    return datetime.utcnow() >= expires_at

def get_google_user_info(access_token: str) -> Dict[str, str]:
    """
    Gets Google user information from access token.
    
    Args:
        access_token: Valid Google OAuth access token
        
    Returns:
        Dictionary containing Google user ID and email
        
    Raises:
        OAuthValidationError: If user info retrieval fails
    """
    try:
        import requests
        
        # Call Google's userinfo endpoint
        response = requests.get(
            'https://www.googleapis.com/oauth2/v1/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        
        if response.status_code == 200:
            user_info = response.json()
            return {
                'google_user_id': user_info.get('id', ''),
                'google_email': user_info.get('email', ''),
                'google_name': user_info.get('name', ''),
                'google_verified_email': user_info.get('verified_email', False)
            }
        else:
            raise OAuthValidationError(f"Failed to get Google user info: HTTP {response.status_code}")
            
    except requests.RequestException as e:
        raise OAuthValidationError(f"Network error getting Google user info: {str(e)}") from e
    except Exception as e:
        raise OAuthValidationError(f"Unexpected error getting Google user info: {str(e)}") from e


def validate_google_account_consistency(user_id: str, new_google_user_id: str, new_google_email: str, region: str) -> Dict[str, Any]:
    """
    Validates if user is connecting the same Google account or switching accounts.
    
    Args:
        user_id: Internal user ID
        new_google_user_id: Google user ID from new OAuth tokens
        new_google_email: Google email from new OAuth tokens
        region: AWS region
        
    Returns:
        Dictionary with validation results and existing account info
        
    Raises:
        OAuthValidationError: If validation fails
    """
    try:
        from utils.secretsmanager_utils import get_oauth_tokens
        
        # Try to get existing OAuth data
        try:
            existing_oauth_data = get_oauth_tokens(user_id, region)
            existing_google_user_id = existing_oauth_data.get('google_user_id')
            existing_google_email = existing_oauth_data.get('google_email')
            
            if existing_google_user_id and existing_google_user_id != new_google_user_id:
                return {
                    'is_account_switch': True,
                    'existing_email': existing_google_email,
                    'new_email': new_google_email,
                    'message': f"Switching from {existing_google_email} to {new_google_email}"
                }
            else:
                return {
                    'is_account_switch': False,
                    'existing_email': existing_google_email,
                    'new_email': new_google_email,
                    'message': "Same Google account or first connection"
                }
                
        except Exception:
            # No existing OAuth data found - first connection
            return {
                'is_account_switch': False,
                'existing_email': None,
                'new_email': new_google_email,
                'message': "First Gmail connection"
            }
            
    except Exception as e:
        raise OAuthValidationError(f"Error validating Google account consistency: {str(e)}") from e