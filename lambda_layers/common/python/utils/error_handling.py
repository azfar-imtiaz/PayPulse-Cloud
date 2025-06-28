import json
import logging

"""
def log_and_generate_error_response(error_code: int, error_message: str, error: Exception = None) -> dict:
    logging.error(error_message)
    response_body = {'message': error_message}
    if error:
        response_body['error'] = str(error)
        logging.error(str(error))
    return {
        'statusCode': error_code,
        'body': json.dumps(response_body)
    }
"""