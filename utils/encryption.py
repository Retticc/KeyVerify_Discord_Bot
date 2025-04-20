from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY is not set in environment variables.")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

# Encrypt a string.
def encrypt_data(data: str) -> str:
    return cipher_suite.encrypt(data.encode()).decode()

# Decrypt a string.
def decrypt_data(data: str) -> str:
    return cipher_suite.decrypt(data.encode()).decode()
