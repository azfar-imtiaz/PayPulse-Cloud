import jwt
import time
import logging

from utils.exceptions import InvalidCredentialsError, JWTGenerationError, TokenExpiredError, InvalidTokenError


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