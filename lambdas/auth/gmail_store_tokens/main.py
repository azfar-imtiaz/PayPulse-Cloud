import os
import json
import boto3
from urllib.parse import parse_qs
from urllib.error import URLError, HTTPError

from utils.decorators import require_auth
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import store_oauth_tokens
from utils.oauth_utils import validate_oauth_tokens, get_google_user_info, validate_google_account_consistency
from utils.s3_utils import create_user_folders_in_s3
from utils.exceptions import (
    SecretsManagerError,
    OAuthValidationError
)

REGION = os.environ['REGION']
S3_BUCKET = os.environ.get('S3_BUCKET', '')

s3_client = boto3.client('s3')

@require_auth
def lambda_handler(event, context, user_id):
    """
    Receives OAuth tokens directly from iOS app and stores them in SecretsManager - requires JWT authentication

    Expected request body:
    {
        'access_token': 'string',
        'refresh_token': 'string',
        'expires_in': 'number',
        'scope': ['string1', 'string2', ...],  // Array of scope strings
        'email': 'string'
    }
    """
    print("Lambda function started")
    print(f"Event keys: {list(event.keys())}")
    print(f"Event headers: {event.get('headers')}")
    print(f"Event body: {event.get('body')}")

    try:
        print(f"Processing OAuth token storage for user: {user_id}")

        headers = event.get('headers', {})
        
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

        # Parse request data (support both JSON and form data)
        content_type = headers.get('content-type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            # Parse form data
            parsed_data = parse_qs(body)
            # parse_qs returns lists, so get first value
            access_token = parsed_data.get('access_token', [None])[0]
            refresh_token = parsed_data.get('refresh_token', [None])[0]
            expires_in = int(parsed_data.get('expires_in', [3600])[0])
            # For form data, scope might be sent as comma-separated string
            scope_raw = parsed_data.get('scope', [''])[0]
            scope = scope_raw if scope_raw else ""
            email = parsed_data.get('email', [None])[0]
            print(f"Parsed form data - access_token: {access_token[:20]}..., refresh_token: {refresh_token[:20] if refresh_token else None}..., email: {email}")
        else:
            # Parse JSON data
            request_body = json.loads(body)
            print(f"Parsed request body: {request_body}")
            access_token = request_body["access_token"]
            refresh_token = request_body.get("refresh_token")
            expires_in = request_body.get("expires_in", 3600)
            # Handle scope as list of strings
            scope_list = request_body.get("scope", [])
            if isinstance(scope_list, list):
                scope = " ".join(scope_list)  # Join list into space-separated string
            else:
                scope = str(scope_list)  # Handle case where it's already a string
            email = request_body.get("email")
        
        print(f"Received tokens - access_token length: {len(access_token)}, refresh_token: {'present' if refresh_token else 'missing'}")
        print(f"Token expires_in: {expires_in}, scope: {scope}")
        
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

        # Create user folder structure in S3 if bucket is configured
        if S3_BUCKET:
            try:
                create_user_folder_in_s3(s3_client, user_id, S3_BUCKET)
                print(f"Created S3 folder structure for user {user_id}")
            except Exception as e:
                print(f"Warning: Failed to create S3 folder structure for user {user_id}: {e}")
                # Don't fail the entire request if folder creation fails

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