import jwt
import time
import quopri
import bcrypt
import logging
from email.header import decode_header

from utils.exceptions import InvalidCredentialsError, JWTGenerationError, TokenExpiredError, InvalidTokenError


def verify_user_password(user_password: str, db_password: str):
    if not bcrypt.checkpw(user_password.encode('utf-8'), db_password.encode('utf-8')):
        logging.warning("Incorrect password provided.")
        raise InvalidCredentialsError("Invalid credentials")
    logging.info("Password verified successfully!")
    return None


def generate_jwt_token(user_id: str, email: str, jwt_secret: str) -> str:
    try:
        payload = {
            "user_id": user_id,
            "email": email,
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400     # 24 hours
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        logging.info("Token generated successfully!")
        return token
    except Exception as e:
        logging.error(f"Error generating JWT token: {e}")
        raise JWTGenerationError("An error occurred while generating the JWT token") from e


def decode_jwt_token(token: str, jwt_secret: str) -> str:
    decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    user_id = decoded['user_id']
    return user_id


def get_user_id_from_token(auth_header: str, jwt_secret: str):
    try:
        if not auth_header:
            raise InvalidCredentialsError("Missing authentication.")
        token = auth_header.split(' ')[1]
        user_id = decode_jwt_token(token, jwt_secret=jwt_secret)
        return user_id
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Expired token.")
    except jwt.InvalidTokenError:
        raise InvalidTokenError("Invalid token.")


def decode_string(s):
    decoded_bytes, charset = decode_header(s)[0]
    decoded_string = decoded_bytes.decode(charset) \
        if isinstance(decoded_bytes, bytes) else decoded_bytes
    return decoded_string


def get_body_from_email(s):
    decoded_bytes = quopri.decodestring(s)
    decoding_string = decoded_bytes.decode('utf-8')
    return decoding_string


