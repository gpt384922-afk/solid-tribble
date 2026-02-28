from cryptography.fernet import Fernet

from crypto.secrets import SecretCipher


def test_encrypt_decrypt_roundtrip() -> None:
    key = Fernet.generate_key().decode("utf-8")
    cipher = SecretCipher(key)

    secret = "my_strong_password"
    encrypted = cipher.encrypt(secret)
    assert encrypted != secret
    assert cipher.decrypt(encrypted) == secret
