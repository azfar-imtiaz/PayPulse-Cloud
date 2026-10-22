import os
import json
import boto3
import requests
from urllib.parse import parse_qs
from urllib.error import URLError, HTTPError

from utils.decorators import require_auth
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.secretsmanager_utils import store_outlook_oauth_tokens
from utils.oauth_utils import validate_oauth_tokens, get_outlook_user_info, validate_outlook_account_consistency
from utils.outlook_api_utils import TOKEN_URL
from utils.s3_utils import create_user_folders_in_s3
from utils.exceptions import (
    SecretsManagerError,
    OAuthValidationError
)

REGION = os.environ['REGION']
S3_BUCKET = os.environ.get('S3_BUCKET', '')
OUTLOOK_OAUTH_CLIENT_ID = os.environ['OUTLOOK_OAUTH_CLIENT_ID']
OUTLOOK_OAUTH_CLIENT_SECRET = os.environ['OUTLOOK_OAUTH_CLIENT_SECRET']
OUTLOOK_REDIRECT_URI = os.environ['OUTLOOK_REDIRECT_URI']

s3_client = boto3.client('s3')


def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """
    Exchanges an OAuth authorization code for an access/refresh token pair via Microsoft's
    token endpoint. The client secret is only ever held here, server-side - the iOS app never
    sees a token of any kind, only the opaque authorization code.
    """
    response = requests.post(TOKEN_URL, data={
        'client_id': OUTLOOK_OAUTH_CLIENT_ID,
        'client_secret': OUTLOOK_OAUTH_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'code_verifier': code_verifier,
        'redirect_uri': OUTLOOK_REDIRECT_URI,
        'scope': 'User.Read Mail.Read offline_access openid email'
    }, timeout=10)

    if response.status_code != 200:
        error_body = response.json() if response.content else {}
        raise OAuthValidationError(f"Outlook code exchange failed: HTTP {response.status_code} - {error_body}")

    return response.json()


@require_auth
def lambda_handler(event, context, user_id):
    """
    Receives an Outlook OAuth authorization code from the iOS app, exchanges it for an
    access/refresh token pair server-side, and stores the tokens in SecretsManager - requires
    JWT authentication.

    Expected request body:
    {
        'code': 'string',
        'code_verifier': 'string'
    }
    """
    print("Lambda function started")
    print(f"Event keys: {list(event.keys())}")
    print(f"Event headers: {event.get('headers')}")
    print(f"Event body: {event.get('body')}")

    try:
        print(f"Processing Outlook OAuth code exchange for user: {user_id}")

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
            code = parsed_data.get('code', [None])[0]
            code_verifier = parsed_data.get('code_verifier', [None])[0]
        else:
            # Parse JSON data
            request_body = json.loads(body)
            print(f"Parsed request body: {request_body}")
            code = request_body["code"]
            code_verifier = request_body["code_verifier"]

        print(f"Received authorization code (length {len(code)}), code_verifier present: {bool(code_verifier)}")

        # Exchange the authorization code for an access/refresh token pair
        token_data = exchange_code_for_tokens(code, code_verifier)
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        scope = token_data.get('scope', '')

        if not refresh_token:
            raise OAuthValidationError("Microsoft's code exchange response did not include a refresh_token")

        print(f"Exchanged code for tokens - access_token length: {len(access_token)}, refresh_token present: {bool(refresh_token)}")
        print(f"Token expires_in: {expires_in}, scope: {scope}")

        # Validate OAuth tokens (basic validation)
        validate_oauth_tokens(access_token, scope)

        # Get Outlook user information from the access token
        outlook_user_info = get_outlook_user_info(access_token)
        print(f"Retrieved Outlook user info for: {outlook_user_info['outlook_email']}")

        # Validate Outlook account consistency (check for account switching)
        consistency_check = validate_outlook_account_consistency(
            user_id=user_id,
            new_outlook_user_id=outlook_user_info['outlook_user_id'],
            new_outlook_email=outlook_user_info['outlook_email'],
            region=REGION
        )

        if consistency_check['is_account_switch']:
            print(f"User {user_id} switching Outlook accounts: {consistency_check['message']}")

        # Store tokens in Secrets Manager with Outlook user info
        store_outlook_oauth_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scope=scope,
            region=REGION,
            outlook_user_info=outlook_user_info
        )

        print(f"Successfully stored Outlook OAuth tokens for user {user_id}")

        # Create user folder structure in S3 if bucket is configured
        if S3_BUCKET:
            try:
                create_user_folders_in_s3(s3_client, user_id, S3_BUCKET)
                print(f"Created S3 folder structure for user {user_id}")
            except Exception as e:
                print(f"Warning: Failed to create S3 folder structure for user {user_id}: {e}")
                # Don't fail the entire request if folder creation fails

        return success_response(
            message="Outlook OAuth tokens stored successfully!",
            data={
                "outlook_email": outlook_user_info['outlook_email'],
                "scope": scope,
                "account_switch": consistency_check['is_account_switch'],
                "message": consistency_check['message']
            },
            status_code=201
        )

    except (URLError, HTTPError, requests.exceptions.RequestException) as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Network error communicating with Microsoft Graph",
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
