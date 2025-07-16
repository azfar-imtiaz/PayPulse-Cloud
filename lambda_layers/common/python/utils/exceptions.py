class InvalidCredentialsError(Exception):
    pass

class UserNotFoundError(Exception):
    pass

class JWTGenerationError(Exception):
    pass

class JWTDecodingError(Exception):
    pass

class TokenExpiredError(Exception):
    pass

class InvalidTokenError(Exception):
    pass

class DatabaseError(Exception):
    pass

class UserAlreadyExistsError(Exception):
    pass

class NoInvoiceFoundError(Exception):
    pass

class S3Error(Exception):
    pass

class SecretsManagerError(Exception):
    pass

class InvoiceParseError(Exception):
    pass