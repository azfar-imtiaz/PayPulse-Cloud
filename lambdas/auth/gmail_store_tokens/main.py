import os
import json
import boto3
import logging
from typing import Dict, Any

from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import store_oauth_tokens
from utils.oauth_utils import validate_oauth_tokens, get_google_user_info, validate_google_account_consistency
from utils.jwt_utils import get_user_id_from_token
from utils.exceptions import (
    JWTDecodingError, 
    InvalidCredentialsError, 
    InvalidTokenError, 
    TokenExpiredError,
    SecretsManagerError,
    OAuthValidationError
)

JWT_SECRET = os.environ['JWT_SECRET']
REGION = os.environ['REGION']

def lambda_handler(event, context):
    """
    Stores OAuth tokens received from iOS app for Gmail API access.
    
    Expected request body:
    {
        "access_token": "string",
        "refresh_token": "string", 
        "expires_in": int,
        "scope": "string"
    }
    """
    try:
        logging.info(f"Received event: {json.dumps(event, default=str)}")
        
        # Get user ID from JWT token
        auth_header = event['headers'].get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
        logging.info(f"Processing OAuth token storage for user: {user_id}")
        
        # Parse request body
        request_body = json.loads(event['body'])
        
        # Extract OAuth tokens
        access_token = request_body['access_token']
        refresh_token = request_body['refresh_token']
        expires_in = request_body.get('expires_in', 3600)  # Default 1 hour
        scope = request_body.get('scope', '')
        
        # Validate OAuth tokens (basic validation)
        validate_oauth_tokens(access_token, refresh_token, scope)
        
        # Get Google user information from the access token
        google_user_info = get_google_user_info(access_token)
        logging.info(f"Retrieved Google user info for: {google_user_info['google_email']}")
        
        # Validate Google account consistency (check for account switching)
        consistency_check = validate_google_account_consistency(
            user_id=user_id,
            new_google_user_id=google_user_info['google_user_id'],
            new_google_email=google_user_info['google_email'],
            region=REGION
        )
        
        if consistency_check['is_account_switch']:
            logging.warning(f"User {user_id} switching Google accounts: {consistency_check['message']}")
        
        # Store tokens in Secrets Manager with Google user info
        store_oauth_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope=scope,
            region=REGION,
            google_user_info=google_user_info
        )
        
        logging.info(f"Successfully stored OAuth tokens for user {user_id}")
        
        return success_response(
            message="Gmail OAuth tokens stored successfully!",
            data={
                "user_id": user_id,
                "google_email": google_user_info['google_email'],
                "scope": scope,
                "account_switch": consistency_check['is_account_switch'],
                "message": consistency_check['message']
            },
            status_code=201
        )
        
    except OAuthValidationError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_CREDENTIALS, 
            "Invalid OAuth tokens", 
            400, 
            e
        )
        
    except InvalidTokenError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_TOKEN, 
            "Malformed JWT Token", 
            401, 
            e
        )
        
    except TokenExpiredError as e:
        return log_and_generate_error_response(
            ErrorCode.TOKEN_EXPIRED, 
            "Expired JWT token", 
            401, 
            e
        )
        
    except JWTDecodingError as e:
        return log_and_generate_error_response(
            ErrorCode.JWT_ERROR, 
            "Error parsing JWT token", 
            500, 
            e
        )
        
    except SecretsManagerError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE, 
            "Error storing OAuth tokens", 
            502, 
            e
        )
        
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(
            ErrorCode.INVALID_JSON, 
            "Invalid JSON in request body", 
            400, 
            e
        )
        
    except KeyError as e:
        return log_and_generate_error_response(
            ErrorCode.MISSING_FIELDS, 
            f"Missing required field in request body: {e}", 
            400, 
            e
        )
        
    except Exception as e:
        return log_and_generate_error_response(
            ErrorCode.INTERNAL_SERVER_ERROR, 
            "Internal Server Error", 
            500, 
            e
        )