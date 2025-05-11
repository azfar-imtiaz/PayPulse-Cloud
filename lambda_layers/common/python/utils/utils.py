import jwt
import time
import bcrypt
import logging

from utils.exceptions import InvalidCredentialsError, JWTGenerationError


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