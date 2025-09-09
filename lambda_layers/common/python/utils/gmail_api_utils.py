import logging
import email
from typing import List, Dict, Any, Optional
from email.message import Message

from google.oauth2.credentials import Credentials as OAuth2Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

from utils.exceptions import GmailAPIError, OAuthValidationError


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
                raise OAuthValidationError(f"Token refresh failed: {str(e)}") from e
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)
        logging.info("Gmail API service created successfully")
        return service
        
    except OAuthValidationError:
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
        
        # Decode the raw message
        import base64
        raw_email = base64.urlsafe_b64decode(message['raw']).decode('utf-8')
        
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

