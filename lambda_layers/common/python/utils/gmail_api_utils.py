import logging
import email
from typing import List, Dict, Any, Optional
from email.message import Message

from google.oauth2.credentials import Credentials as OAuth2Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

from utils.exceptions import GmailAPIError, OAuthValidationError, RefreshTokenExpiredError


def create_gmail_service(user_id: str, access_token: str, refresh_token: str, client_id: str, region: str, client_secret: str = None, expires_at: str = None):
    """
    Creates a Gmail API service object using OAuth credentials with automatic token refresh.
    
    Args:
        user_id: User ID for token updates
        access_token: OAuth access token
        refresh_token: OAuth refresh token  
        client_id: Google OAuth client ID
        region: AWS region for Secrets Manager
        client_secret: OAuth client secret (None for iOS public clients)
        expires_at: Token expiration timestamp in ISO format
        
    Returns:
        Gmail API service object
        
    Raises:
        GmailAPIError: If service creation fails
        OAuthValidationError: If token refresh fails
    """
    try:
        # Check if token needs refresh
        from datetime import datetime, timedelta
        from utils.secretsmanager_utils import update_oauth_tokens
        import dateutil.parser
        
        # Create credentials object (use empty string for iOS OAuth public clients)
        credentials = OAuth2Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret or "",  # Empty string for iOS OAuth public clients
            token_uri="https://oauth2.googleapis.com/token",
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        # Check if token is expired or will expire soon, and refresh proactively
        
        should_refresh = False
        
        # Check expiration using the stored expires_at timestamp
        if expires_at:
            try:
                expiry_time = dateutil.parser.isoparse(expires_at).replace(tzinfo=None)
                current_time = datetime.utcnow()
                time_until_expiry = expiry_time - current_time
                
                # Refresh if expired or expiring within 5 minutes
                should_refresh = time_until_expiry < timedelta(minutes=5)
                logging.info(f"Token expires in {time_until_expiry.total_seconds():.0f} seconds")
                
            except Exception as e:
                logging.warning(f"Could not parse expires_at '{expires_at}': {e}. Checking credentials.expired")
                should_refresh = credentials.expired
        else:
            # Fallback to credentials.expired if no expires_at provided
            should_refresh = credentials.expired
            
        if should_refresh:
            logging.info("Access token expired or expiring soon, refreshing...")
            try:
                # Import here to avoid circular imports
                import google.auth.transport.requests
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                
                # Update tokens in Secrets Manager
                new_expires_in = int((credentials.expiry - datetime.utcnow()).total_seconds()) if credentials.expiry else 3600
                update_oauth_tokens(
                    user_id=user_id,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token or refresh_token,
                    expires_in=new_expires_in,
                    region=region
                )
                logging.info("Access token refreshed and updated in Secrets Manager")
                
            except RefreshError as e:
                error_str = str(e)
                # Check if this is an expired/revoked refresh token
                if 'invalid_grant' in error_str and ('expired' in error_str or 'revoked' in error_str):
                    logging.warning(f"Refresh token expired/revoked for user {user_id}. Clearing tokens.")
                    # Clear the expired tokens from Secrets Manager
                    from utils.secretsmanager_utils import delete_oauth_tokens
                    try:
                        delete_oauth_tokens(user_id, region)
                    except Exception as delete_error:
                        logging.error(f"Failed to clear expired tokens: {delete_error}")

                    raise RefreshTokenExpiredError(f"Refresh token has expired or been revoked. Please re-connect your Gmail account.") from e
                else:
                    raise OAuthValidationError(f"Token refresh failed: {str(e)}") from e
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)
        logging.info("Gmail API service created successfully")
        return service
        
    except (OAuthValidationError, RefreshTokenExpiredError):
        raise
    except Exception as e:
        raise GmailAPIError(f"Failed to create Gmail API service: {str(e)}") from e


def search_emails(service, sender: str, subject: str = "", since_date: str = "") -> List[Dict[str, Any]]:
    """
    Searches for emails using Gmail API.
    
    Args:
        service: Gmail API service object
        sender: Email sender to search for
        subject: Email subject to search for (optional)
        since_date: Date to search from in format "YYYY/MM/DD" (optional)
        
    Returns:
        List of email message IDs and thread IDs
        
    Raises:
        GmailAPIError: If search fails
    """
    try:
        # Build search query
        query_parts = [f'from:{sender}']
        
        if subject:
            query_parts.append(f'subject:"{subject}"')
            
        if since_date:
            query_parts.append(f'after:{since_date}')
            
        query = ' '.join(query_parts)
        logging.info(f"Gmail API search query: {query}")
        
        # Execute search
        result = service.users().messages().list(userId='me', q=query).execute()
        messages = result.get('messages', [])
        
        logging.info(f"Found {len(messages)} messages")
        return messages
        
    except Exception as e:
        raise GmailAPIError(f"Gmail API search failed: {str(e)}") from e


def get_email_content(service, message_id: str) -> Message:
    """
    Gets the full email content using Gmail API.
    Returns the same Message format that download_and_upload_attachment expects.
    
    Args:
        service: Gmail API service object
        message_id: Gmail message ID
        
    Returns:
        Email message object (compatible with download_and_upload_attachment)
        
    Raises:
        GmailAPIError: If email retrieval fails
    """
    try:
        # Get message in raw format
        message = service.users().messages().get(
            userId='me', 
            id=message_id, 
            format='raw'
        ).execute()
        
        # Decode the raw message with robust encoding handling
        import base64
        raw_email_bytes = base64.urlsafe_b64decode(message['raw'])

        # Try multiple encodings to handle international characters
        encodings_to_try = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
        raw_email = None

        for encoding in encodings_to_try:
            try:
                raw_email = raw_email_bytes.decode(encoding)
                logging.info(f"Successfully decoded email using {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue

        if raw_email is None:
            # Fallback: decode with errors='replace' to avoid crashes
            raw_email = raw_email_bytes.decode('utf-8', errors='replace')
            logging.warning(f"Used UTF-8 with error replacement for message {message_id}")
        
        # Parse email - this returns the same Message object format that IMAP used
        email_message = email.message_from_string(raw_email)
        logging.info(f"Retrieved email with subject: {email_message.get('Subject', 'No Subject')}")
        
        return email_message
        
    except Exception as e:
        raise GmailAPIError(f"Failed to get email content: {str(e)}") from e


def get_latest_email_by_date(service, sender: str, subject: str, target_month: int, target_year: int) -> Optional[Message]:
    """
    Gets the latest email for a specific month/year.
    
    Args:
        service: Gmail API service object
        sender: Email sender
        subject: Email subject
        target_month: Target month (1-12)
        target_year: Target year
        
    Returns:
        Email message object if found, None otherwise
    """
    try:
        # Format search date (first day of target month)
        search_date = f"{target_year}/{target_month:02d}/01"
        
        # Search for emails
        messages = search_emails(service, sender, subject, search_date)
        
        if not messages:
            logging.info(f"No emails found for {target_month}/{target_year}")
            return None
            
        # Get the latest message (Gmail returns in reverse chronological order)
        latest_message_id = messages[0]['id']
        email_content = get_email_content(service, latest_message_id)
        
        # Verify the email date matches target month/year
        email_date_str = email_content.get('Date')
        if email_date_str:
            from email.utils import parsedate_to_datetime
            email_date = parsedate_to_datetime(email_date_str)
            
            if email_date.year == target_year and email_date.month == target_month:
                logging.info(f"Found matching email for {target_month}/{target_year}")
                return email_content
            else:
                logging.info(f"Email date {email_date.month}/{email_date.year} doesn't match target {target_month}/{target_year}")
                
        return None
        
    except GmailAPIError:
        raise
    except Exception as e:
        raise GmailAPIError(f"Failed to get latest email by date: {str(e)}") from e


def build_gmail_query(email_patterns: List[str], subject_keywords: List,
                      start_date: str, end_date: str) -> str:
    """
    Build Gmail search query from vendor config with support for mixed AND/OR logic

    Args:
        email_patterns: List of email addresses (e.g., ["domino@dominos.se"])
        subject_keywords: List of keywords or keyword objects:
            - String: "Receipt for Order #"
            - Object: {"keywords": ["Order #", "confirmed"], "logic": "AND"}
        start_date: Start date "YYYY/MM/DD"
        end_date: End date "YYYY/MM/DD"

    Returns:
        Gmail query string

    Example output:
        '(from:domino@dominos.se) (subject:"Receipt for Order #" OR (subject:"Order #" subject:"confirmed")) after:2024/01/01 before:2024/01/31'
    """
    # Build FROM clause (OR multiple email patterns)
    from_clause = " OR ".join([f"from:{email}" for email in email_patterns])
    if len(email_patterns) > 1:
        from_clause = f"({from_clause})"

    # Build SUBJECT clause with support for mixed AND/OR logic
    subject_clause = ""
    if subject_keywords:
        subject_parts = []

        for keyword_item in subject_keywords:
            if isinstance(keyword_item, str):
                # Simple string keyword
                subject_parts.append(f'subject:"{keyword_item}"')
            elif isinstance(keyword_item, dict):
                # Complex keyword object with logic
                keywords = keyword_item.get('keywords', [])
                logic = keyword_item.get('logic', 'OR').upper()

                if not keywords:
                    continue

                if logic == 'AND':
                    # For AND: subject:"term1" subject:"term2"
                    and_part = " ".join([f'subject:"{kw}"' for kw in keywords])
                    if len(keywords) > 1:
                        and_part = f"({and_part})"
                    subject_parts.append(and_part)
                else:
                    # For OR: subject:"term1" OR subject:"term2"
                    or_part = " OR ".join([f'subject:"{kw}"' for kw in keywords])
                    if len(keywords) > 1:
                        or_part = f"({or_part})"
                    subject_parts.append(or_part)

        if subject_parts:
            # Combine all subject parts with OR
            if len(subject_parts) > 1:
                subject_clause = f"({' OR '.join(subject_parts)})"
            else:
                subject_clause = subject_parts[0]

    # Combine with date range
    query_parts = [from_clause]
    if subject_clause:
        query_parts.append(subject_clause)
    query_parts.append(f"after:{start_date}")
    query_parts.append(f"before:{end_date}")

    query = " ".join(query_parts)
    logging.info(f"Built Gmail query: {query}")
    return query


def build_sweep_gmail_query(start_date: str, end_date: str, excluded_senders: List[str] = None) -> str:
    """
    Build a broad, date-bounded Gmail search query for the retail invoice sweep pipeline.

    Unlike build_gmail_query, this has no from:/subject: scoping at all - that's exactly
    the hardcoded vendor-driven behavior this pipeline replaces. Only cheap, non-LLM
    excludes are applied to cut obvious noise before any classification call.

    Args:
        start_date: Start date "YYYY/MM/DD"
        end_date: End date "YYYY/MM/DD"
        excluded_senders: Email addresses to exclude via -from: clauses - for senders that
            belong entirely to a different pipeline (e.g. kundservice@wallenstam.se is
            already handled by fetch_latest_invoice/rental) and should never reach Jev
            classification at all, rather than relying on the LLM to recognize and reject
            them every time.

    Returns:
        Gmail query string, e.g.
        "after:2026/09/01 before:2026/10/05 -in:chats -in:sent -in:drafts -in:trash -in:spam -from:kundservice@wallenstam.se"
    """
    query = f"after:{start_date} before:{end_date} -in:chats -in:sent -in:drafts -in:trash -in:spam"
    for sender in (excluded_senders or []):
        query += f" -from:{sender}"
    logging.info(f"Built sweep Gmail query: {query}")
    return query


def get_email_metadata_light(service, message_id: str) -> Dict[str, Any]:
    """
    Fetch lightweight email metadata (Subject, From headers + snippet) without pulling
    the full raw MIME body. Used by the sweep/classification pipeline to keep per-message
    cost low across a much larger candidate pool than vendor-scoped fetching - full body
    fetch (get_email_content) is deferred until a message survives classification and
    needs Tier 3 extraction.

    Args:
        service: Gmail API service object
        message_id: Gmail message ID

    Returns:
        Dict with keys: message_id, subject, sender, snippet

    Raises:
        GmailAPIError: If metadata retrieval fails
    """
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=['Subject', 'From']
        ).execute()

        headers = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}

        return {
            'message_id': message_id,
            'subject': headers.get('Subject', ''),
            'sender': headers.get('From', ''),
            'snippet': message.get('snippet', ''),
        }
    except Exception as e:
        raise GmailAPIError(f"Failed to get email metadata: {str(e)}") from e


def derive_vendor_slug_from_sender(from_header: str) -> str:
    """
    Derive a vendor slug from a sender's email domain, for S3 key/filename purposes only.

    This is NOT the authoritative vendor name - that comes from Gemini's extraction
    output (vendor_name field) after Tier 3 parsing, same as today. This slug exists
    purely because generate_retail_invoice_s3_key() needs a vendor_id string before
    extraction has happened, now that VendorConfig isn't driving discovery.

    Args:
        from_header: Raw "From" header value, e.g. '"Elgiganten" <noreply@elgiganten.se>'

    Returns:
        A lowercase slug derived from the domain's second-level name, e.g. "elgiganten".
        Falls back to "unknown-vendor" if no parseable email address is found.
    """
    import re

    match = re.search(r'[\w.+-]+@([\w.-]+)', from_header or '')
    if not match:
        return "unknown-vendor"

    domain = match.group(1).lower()
    parts = domain.split('.')
    # e.g. "noreply@elgiganten.se" -> "elgiganten"; "orders@mail.foodora.se" -> "foodora"
    slug = parts[-2] if len(parts) >= 2 else parts[0]
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug or "unknown-vendor"


def extract_html_from_email(email_message: Message) -> str:
    """
    Extract HTML body from email message

    Args:
        email_message: Email Message object

    Returns:
        HTML content as string
    """
    html_body = None

    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()

            # Prefer HTML over plain text
            if content_type == 'text/html':
                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
            elif content_type == 'text/plain' and html_body is None:
                # Fallback to plain text if no HTML
                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
    else:
        # Not multipart
        html_body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')

    return html_body or ""

