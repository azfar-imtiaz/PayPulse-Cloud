import os
import json
import logging
from urllib.request import Request, urlopen
from urllib.parse import urlencode, parse_qs
from urllib.error import URLError, HTTPError

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
GOOGLE_WEB_CLIENT_ID = os.environ["GOOGLE_WEB_CLIENT_ID"]
GOOGLE_WEB_CLIENT_SECRET = os.environ["GOOGLE_WEB_CLIENT_SECRET"]
TOKEN_URL = "https://oauth2.googleapis.com/token"

def lambda_handler(event, context):
    """
    Receives auth code and email from iOS app, uses those to get access token and refresh token
    from Google, and store those in SecretsManager

    Expected request body:
    {
        'auth_code': 'string',
        'email': 'string'
    }
    """
    print("Lambda function started")
    print(f"Event keys: {list(event.keys())}")
    print(f"Event headers: {event.get('headers')}")
    print(f"Event body: {event.get('body')}")
    
    try:
        # Get user ID from JWT token
        headers = event.get('headers', {})
        auth_header = headers.get('authorization')
        user_id = get_user_id_from_token(auth_header, JWT_SECRET)
        print(f"Processing OAuth token storage for user: {user_id}")
        
        body = event.get('body')
        print(f"Raw body received: {repr(body)}")
        print(f"Body type: {type(body)}")
        print(f"Is base64 encoded: {event.get('isBase64Encoded', False)}")
        
        if not body:
            raise ValueError("Request body is empty!")

        if event.get('isBase64Encoded', False):
            import base64
            body = base64.b64decode(body).decode('utf-8')
            print(f"Decoded body: {repr(body)}")

        # Parse URL-encoded form data instead of JSON
        content_type = headers.get('content-type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            # Parse form data
            parsed_data = parse_qs(body)
            # parse_qs returns lists, so get first value
            auth_code = parsed_data.get('authCode', [None])[0]
            email = parsed_data.get('email', [None])[0]
            print(f"Parsed form data - authCode: {auth_code}, email: {email}")
        else:
            # Fall back to JSON parsing
            request_body = json.loads(body)
            print(f"Parsed request body: {request_body}")
            auth_code = request_body["auth_code"]
            email = request_body["email"]

        payload = {
            "code": auth_code,
            "client_id": GOOGLE_WEB_CLIENT_ID,
            "client_secret": GOOGLE_WEB_CLIENT_SECRET,
            "redirect_uri": "postmessage",
            "grant_type": "authorization_code"
        }
        
        print(f"Using client_id: {GOOGLE_WEB_CLIENT_ID}")
        print(f"Using client_secret: {GOOGLE_WEB_CLIENT_SECRET[:20]}...")  # Show first 20 chars
        print(f"Auth code length: {len(auth_code)}")
        print(f"Payload for Google: {payload}")
        
        # Prepare POST request
        data = urlencode(payload).encode('utf-8')
        request = Request(
            TOKEN_URL,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                error_text = response.read().decode('utf-8')
                raise OAuthValidationError(f"Failed to get OAuth tokens from Google: {response.status} -> {error_text}")
            token_data = json.loads(response.read().decode('utf-8'))

        # Extract OAuth tokens
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
        scope = token_data.get('scope', '')
        
        # Validate OAuth tokens (basic validation)
        validate_oauth_tokens(access_token, scope)
        
        # Get Google user information from the access token
        google_user_info = get_google_user_info(access_token)
        print(f"Retrieved Google user info for: {google_user_info['google_email']}")
        
        # Validate Google account consistency (check for account switching)
        consistency_check = validate_google_account_consistency(
            user_id=user_id,
            new_google_user_id=google_user_info['google_user_id'],
            new_google_email=google_user_info['google_email'],
            region=REGION
        )
        
        if consistency_check['is_account_switch']:
            print(f"User {user_id} switching Google accounts: {consistency_check['message']}")
        
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
        
        print(f"Successfully stored OAuth tokens for user {user_id}")
        
        return success_response(
            message="Gmail OAuth tokens stored successfully!",
            data={
                # "user_id": user_id,
                "google_email": google_user_info['google_email'],
                "scope": scope,
                "account_switch": consistency_check['is_account_switch'],
                "message": consistency_check['message']
            },
            status_code=201
        )
        
    except (URLError, HTTPError) as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Network error communicating with Google",
            502,
            e
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
            f"Internal Server Error: {e}",
            500, 
            e
        )