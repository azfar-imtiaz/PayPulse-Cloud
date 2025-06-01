import bcrypt
import logging

from utils.exceptions import InvalidCredentialsError


def verify_user_password(user_password: str, db_password: str):
    if not bcrypt.checkpw(user_password.encode('utf-8'), db_password.encode('utf-8')):
        logging.warning("Incorrect password provided.")
        raise InvalidCredentialsError("Invalid credentials")
    logging.info("Password verified successfully!")
    return None


def create_password_hash(password: str) -> str:
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed_password.decode('utf-8')
