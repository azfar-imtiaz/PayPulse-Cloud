import base64
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


def create_outlook_client(user_id: str, access_token: str, refresh_token: str, client_id: str, region: str,
                           client_secret: str = None, expires_at: str = None) -> OutlookClient:
    """
    Creates an OutlookClient for Microsoft Graph calls, refreshing the access token first
    if it's expired or expiring soon.

    Args:
        user_id: User ID for token updates
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        client_id: Microsoft Entra application (client) ID
        region: AWS region for Secrets Manager
        client_secret: Microsoft Entra application client secret - required for the refresh
            call now that the app registration is a confidential client (Microsoft rejects
            a client_secret-less refresh with AADSTS70002).
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
                'client_secret': client_secret,
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
        Dict with keys: message_id, subject, sender, snippet, has_attachment

    Raises:
        OutlookAPIError: If metadata retrieval fails
    """
    try:
        response = client.session.get(
            f"{GRAPH_BASE_URL}/me/messages/{message_id}",
            params={'$select': 'subject,from,bodyPreview,hasAttachments'},
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
            'has_attachment': message.get('hasAttachments', False),
        }
    except OutlookAPIError:
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to get Outlook email metadata: {str(e)}") from e


def get_pdf_attachment_bytes(client: OutlookClient, message_id: str) -> Optional[bytes]:
    """
    Fetch the first PDF attachment's bytes for a Graph message, if any. Graph returns
    attachment content inline as base64 contentBytes for normal-sized attachments - the
    $value endpoint (needed for unusually large attachments) is intentionally not handled
    here; oversized attachments are filtered out by the caller's size cap instead.

    Args:
        client: OutlookClient
        message_id: Graph message ID

    Returns:
        Decoded PDF bytes, or None if there's no PDF attachment.

    Raises:
        OutlookAPIError: If the attachments list fails to load.
    """
    try:
        # No $select here deliberately: contentBytes only exists on the fileAttachment
        # subtype, not the polymorphic base "attachment" type the collection is typed as -
        # Graph rejects $select-ing it at the collection level ("Could not find a property
        # named 'contentBytes' on type microsoft.graph.attachment"). $select is exclusive
        # (only listed properties come back), so there's no safe subset that includes it;
        # fetching the full attachment objects is the only way to get contentBytes here.
        response = client.session.get(
            f"{GRAPH_BASE_URL}/me/messages/{message_id}/attachments",
            timeout=15
        )

        if response.status_code != 200:
            raise OutlookAPIError(f"Graph list attachments failed: HTTP {response.status_code} - {response.text}")

        for attachment in response.json().get('value', []):
            name = attachment.get('name', '') or ''
            content_type = attachment.get('contentType', '') or ''
            if content_type == 'application/pdf' or name.lower().endswith('.pdf'):
                content_bytes_b64 = attachment.get('contentBytes')
                if content_bytes_b64:
                    return base64.b64decode(content_bytes_b64)
        return None
    except OutlookAPIError:
        raise
    except Exception as e:
        raise OutlookAPIError(f"Failed to get Outlook PDF attachment: {str(e)}") from e


def get_message_content(client: OutlookClient, message_id: str) -> Dict[str, Any]:
    """
    Gets the full message content (including body) for a Graph message.

    Args:
        client: OutlookClient
        message_id: Graph message ID

    Returns:
        Full message JSON from Graph (includes body.content, body.contentType, from, subject,
        receivedDateTime)

    Raises:
        OutlookAPIError: If message retrieval fails
    """
    try:
        response = client.session.get(
            f"{GRAPH_BASE_URL}/me/messages/{message_id}",
            params={'$select': 'subject,from,body,receivedDateTime'},
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

    Same regex-based logic as gmail_api_utils.derive_vendor_slug_from_sender (both
    providers' sender strings end up in the same "Name <email@domain>" shape by the time
    they reach this function) - duplicated here rather than imported, since
    gmail_api_utils.py has a module-level `googleapiclient` import that isn't available
    in this Lambda's layers (google_api_layer was deliberately dropped - this Lambda
    doesn't call the Gmail API), which made the cross-import fail at call time in
    production with "No module named 'googleapiclient'".

    Args:
        from_field: Sender string, e.g. "Elgiganten <noreply@elgiganten.se>"

    Returns:
        A lowercase slug derived from the domain's second-level name, e.g. "elgiganten".
        Falls back to "unknown-vendor" if no parseable email address is found.
    """
    import re

    match = re.search(r'[\w.+-]+@([\w.-]+)', from_field or '')
    if not match:
        return "unknown-vendor"

    domain = match.group(1).lower()
    parts = domain.split('.')
    slug = parts[-2] if len(parts) >= 2 else parts[0]
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug or "unknown-vendor"
