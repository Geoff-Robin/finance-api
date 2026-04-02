"""
Utility module for standard operational needs, including hash checking.
"""
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

def hash_password(password: str) -> str:
    """
    Encrypts a plaintext password using the argon2 hashing algorithm.

    Args:
        password (str): The raw plaintext user password.

    Returns:
        str: The securely hashed string representation.
    """
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """
    Validates a plaintext password against a stored hashed standard.

    Args:
        password (str): The raw plaintext password to check.
        hashed (str): The stored secure hash representing the correct password.

    Returns:
        bool: True if the password correctly resolves to the hash.
    """
    return pwd_context.verify(password, hashed)
