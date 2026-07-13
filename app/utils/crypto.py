from cryptography.fernet import Fernet


class TokenCipher:
    """Symmetric encryption for secrets at rest (Plaid access tokens).

    Key rotation, KMS, etc. can replace this class without callers
    changing — they only see encrypt/decrypt of strings.
    """

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY is not set — generate one with: "
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
