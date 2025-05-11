class InvalidCredentialsError(Exception):
    pass

class UserNotFoundError(Exception):
    pass

class JWTGenerationError(Exception):
    pass

class DatabaseError(Exception):
    pass

class UserAlreadyExistsError(Exception):
    pass

class S3Error(Exception):
    pass

class SecretsManagerError(Exception):
    pass