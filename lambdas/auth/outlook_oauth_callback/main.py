from urllib.parse import urlencode

MOBILE_REDIRECT_URI = "msauth.com.azfarimtiaz.paypulse://auth"


def lambda_handler(event, context):
    """
    Unauthenticated bounce endpoint. Microsoft's /authorize redirect must land on a
    Web-platform https:// URL (required for the confidential-client code exchange in
    outlook_store_tokens), but the iOS app's ASWebAuthenticationSession can only intercept
    the app's own custom URL scheme. This Lambda just relays the query params from
    Microsoft's redirect straight back to that custom scheme so the app's existing
    interception logic needs no changes.
    """
    params = event.get('queryStringParameters') or {}

    if 'error' in params:
        query = {'error': params['error']}
        if 'error_description' in params:
            query['error_description'] = params['error_description']
    else:
        query = {'code': params.get('code', '')}

    redirect_url = f"{MOBILE_REDIRECT_URI}?{urlencode(query)}"

    return {
        "statusCode": 302,
        "headers": {
            "Location": redirect_url
        }
    }
