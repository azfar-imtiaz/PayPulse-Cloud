import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

import requests
import dateutil.parser

from utils.exceptions import OutlookAPIError, OAuthValidationError, RefreshTokenExpiredError

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


class OutlookClient:
    """Thin wrapper around a requests.Session pre-authorized for Microsoft Graph calls."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        })


def create_outlook_client(user_id: str, access_token: str, refresh_token: str, client_id: str, region: str, expires_at: str = None) -> OutlookClient:
    """
    Creates an OutlookClient for Microsoft Graph calls, refreshing the access token first
    if it's expired or expiring soon.

    Args:
        user_id: User ID for token updates
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        client_id: Microsoft Entra application (client) ID
        region: AWS region for Secrets Manager
        expires_at: Token expiration timestamp in ISO format

    Returns:
        OutlookClient ready to call Graph endpoints

    Raises:
        OutlookAPIError: If client creation fails
        RefreshTokenExpiredError: If the refresh token has expired/been revoked
        OAuthValidationError: If token refresh fails for another reason
    """
    try:
        from utils.secretsmanager_utils import update_outlook_oauth_tokens, delete_outlook_oauth_tokens

        should_refresh = False

        if expires_at:
            try:
                expiry_time = dateutil.parser.isoparse(expires_at).replace(tzinfo=None)
                current_time = datetime.utcnow()
                time_until_expiry = expiry_time - current_time
                should_refresh = time_until_expiry < timedelta(minutes=5)
                logging.info(f"Outlook token expires in {time_until_expiry.total_seconds():.0f} seconds")
            except Exception as e:
                logging.warning(f"Could not parse expires_at '{expires_at}': {e}. Refreshing to be safe.")
                should_refresh = True

        if should_refresh:
            logging.info("Outlook access token expired or expiring soon, refreshing...")

            response = requests.post(TOKEN_URL, data={
                'client_id': client_id,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'scope': 'User.Read Mail.Read offline_access openid email'
            }, timeout=10)

            if response.status_code != 200:
                error_body = response.json() if response.content else {}
                error_code = error_body.get('error', '')

                if error_code == 'invalid_grant':
                    logging.warning(f"Outlook refresh token expired/revoked for user {user_id}. Clearing tokens.")
                    try:
                        delete_outlook_oauth_tokens(user_id, region)
                    except Exception as delete_error:
                        logging.error(f"Failed to clear expired Outlook tokens: {delete_error}")

                    raise RefreshTokenExpiredError("Outlook refresh token has expired or been revoked. Please re-connect your Outlook account.")
                else:
                    raise OAuthValidationError(f"Outlook token refresh failed: HTTP {response.status_code} - {error_body}")

            token_data = response.json()
            new_access_token = token_data['access_token']
            new_refresh_token = token_data.get('refresh_token')

            if not new_refresh_token:
                raise OAuthValidationError("Microsoft's refresh response did not include a new refresh_token - cannot proceed safely")

            # Critical: always persist Microsoft's new refresh_token unconditionally - never
            # fall back to the old one. See plan doc for why.
            update_outlook_oauth_tokens(
                user_id=user_id,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_in=token_data.get('expires_in', 3600),
                region=region
            )
            logging.info("Outlook access token refreshed and updated in Secrets Manager")

            access_token = new_access_token

        return OutlookClient(access_token)

    except (OutlookAPIError, OAuthValidationError, RefreshTokenExpiredError):
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to create Outlook client: {str(e)}") from e


def build_sweep_outlook_query(start_date: str, end_date: str, excluded_senders: List[str] = None) -> str:
    """
    Build a broad, date-bounded Graph OData $filter for the retail invoice sweep pipeline.
    Mirrors build_sweep_gmail_query's intent - no from:/subject: scoping, just a date
    window and cheap sender excludes.

    Args:
        start_date: Start date in ISO 8601 format, e.g. "2026-09-01T00:00:00Z"
        end_date: End date in ISO 8601 format, e.g. "2026-10-05T00:00:00Z"
        excluded_senders: Email addresses to exclude via ne clauses

    Returns:
        Graph OData $filter string
    """
    query = f"receivedDateTime ge {start_date} and receivedDateTime le {end_date}"
    for sender in (excluded_senders or []):
        query += f" and from/emailAddress/address ne '{sender}'"
    logging.info(f"Built sweep Outlook query filter: {query}")
    return query


def list_messages(client: OutlookClient, query_filter: str, page_url: str = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Lists messages in the user's mailbox matching query_filter, paginating via @odata.nextLink.

    Args:
        client: OutlookClient
        query_filter: Graph OData $filter string (ignored on subsequent pages - page_url
            already encodes it)
        page_url: Full URL for the next page (from a prior call's returned next_link), or
            None to start from the first page

    Returns:
        (messages, next_link_or_None)

    Raises:
        OutlookAPIError: If the request fails
    """
    try:
        if page_url:
            response = client.session.get(page_url, timeout=15)
        else:
            response = client.session.get(
                f"{GRAPH_BASE_URL}/me/messages",
                params={'$filter': query_filter, '$select': 'id', '$top': 50},
                timeout=15
            )

        if response.status_code != 200:
            raise OutlookAPIError(f"Graph list messages failed: HTTP {response.status_code} - {response.text}")

        data = response.json()
        messages = data.get('value', [])
        next_link = data.get('@odata.nextLink')

        logging.info(f"Listed {len(messages)} messages, next_link: {'present' if next_link else 'none'}")
        return messages, next_link

    except OutlookAPIError:
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to list Outlook messages: {str(e)}") from e


def get_email_metadata_light(client: OutlookClient, message_id: str) -> Dict[str, Any]:
    """
    Fetch lightweight email metadata (subject, sender, snippet) without pulling the full
    body. Mirrors Gmail's get_email_metadata_light for the same two-stage cost optimization.

    Args:
        client: OutlookClient
        message_id: Graph message ID

    Returns:
        Dict with keys: message_id, subject, sender, snippet

    Raises:
        OutlookAPIError: If metadata retrieval fails
    """
    try:
        response = client.session.get(
            f"{GRAPH_BASE_URL}/me/messages/{message_id}",
            params={'$select': 'subject,from,bodyPreview'},
            timeout=15
        )

        if response.status_code != 200:
            raise OutlookAPIError(f"Graph get message metadata failed: HTTP {response.status_code} - {response.text}")

        message = response.json()
        from_field = message.get('from', {}).get('emailAddress', {})
        sender = f"{from_field.get('name', '')} <{from_field.get('address', '')}>".strip()

        return {
            'message_id': message_id,
            'subject': message.get('subject', ''),
            'sender': sender,
            'snippet': message.get('bodyPreview', ''),
        }
    except OutlookAPIError:
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to get Outlook email metadata: {str(e)}") from e


def get_message_content(client: OutlookClient, message_id: str) -> Dict[str, Any]:
    """
    Gets the full message content (including body) for a Graph message.

    Args:
        client: OutlookClient
        message_id: Graph message ID

    Returns:
        Full message JSON from Graph (includes body.content, body.contentType, from, subject)

    Raises:
        OutlookAPIError: If message retrieval fails
    """
    try:
        response = client.session.get(
            f"{GRAPH_BASE_URL}/me/messages/{message_id}",
            params={'$select': 'subject,from,body'},
            timeout=15
        )

        if response.status_code != 200:
            raise OutlookAPIError(f"Graph get message failed: HTTP {response.status_code} - {response.text}")

        return response.json()
    except OutlookAPIError:
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to get Outlook message content: {str(e)}") from e


def extract_html_from_outlook_message(message_json: Dict[str, Any]) -> str:
    """
    Extract HTML (or plain text, as a fallback) body from a Graph message JSON payload.
    Near no-op compared to Gmail's MIME walk - Graph already returns body.content directly.

    Args:
        message_json: Full message JSON from get_message_content

    Returns:
        HTML (or plain text) content as string
    """
    body = message_json.get('body', {})
    return body.get('content', '') or ''


def derive_vendor_slug_from_sender(from_field: str) -> str:
    """
    Derive a vendor slug from a sender string, for S3 key/filename purposes only.
    Reuses Gmail's regex-based slug function - both providers' sender strings end up in
    the same "Name <email@domain>" shape by the time they reach this function (see
    get_email_metadata_light's sender formatting above).

    Args:
        from_field: Sender string, e.g. "Elgiganten <noreply@elgiganten.se>"

    Returns:
        A lowercase slug derived from the domain's second-level name, e.g. "elgiganten".
    """
    from utils.gmail_api_utils import derive_vendor_slug_from_sender as gmail_derive_vendor_slug
    return gmail_derive_vendor_slug(from_field)
