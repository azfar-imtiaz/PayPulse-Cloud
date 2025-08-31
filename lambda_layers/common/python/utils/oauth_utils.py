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

def prepare_oauth_secret_data(access_token: str, refresh_token: str, expires_in: int, scope: str) -> Dict[str, Any]:
    """
    Prepares OAuth token data for storage in Secrets Manager.
    
    Args:
        access_token: The OAuth access token
        refresh_token: The OAuth refresh token
        expires_in: Token expiration time in seconds
        scope: The granted scope
        
    Returns:
        Dictionary containing formatted OAuth data
    """
    
    import time
    from datetime import datetime, timedelta
    
    # Calculate expiration timestamp
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token, 
        "expires_at": expires_at.isoformat(),
        "expires_in": expires_in,
        "scope": scope,
        "token_type": "Bearer",
        "created_at": datetime.utcnow().isoformat()
    }

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