"""
Encryption layer for soul-legacy.
Uses Fernet (AES-128-CBC + HMAC-SHA256) from cryptography package.
Key derivation: PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP 2023).
Future: swap in age encryption for cross-platform key sharing.
"""
import os, base64, json, hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


ITERATIONS = 600_000


def derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def generate_salt() -> bytes:
    return os.urandom(32)


def encrypt(data: str, passphrase: str, salt: bytes) -> bytes:
    key = derive_key(passphrase, salt)
    f   = Fernet(key)
    return f.encrypt(data.encode())


def decrypt(token: bytes, passphrase: str, salt: bytes) -> str:
    key = derive_key(passphrase, salt)
    f   = Fernet(key)
    return f.decrypt(token).decode()


def encrypt_file(path: str, passphrase: str) -> str:
    """Encrypt a file in-place, returns .enc path"""
    salt    = generate_salt()
    data    = open(path, "rb").read()
    key     = derive_key(passphrase, salt)
    token   = Fernet(key).encrypt(data)
    enc_path = path + ".enc"
    with open(enc_path, "wb") as f:
        f.write(salt + b"||" + token)
    return enc_path


def decrypt_file(enc_path: str, passphrase: str) -> bytes:
    raw     = open(enc_path, "rb").read()
    salt, token = raw.split(b"||", 1)
    key     = derive_key(passphrase, salt)
    return Fernet(key).decrypt(token)


def vault_fingerprint(vault_dir: str) -> str:
    """SHA-256 hash of all vault contents — used for blockchain anchoring"""
    h = hashlib.sha256()
    for root, _, files in os.walk(vault_dir):
        for fname in sorted(files):
            if fname.endswith(".enc"):
                h.update(open(os.path.join(root, fname), "rb").read())
    return h.hexdigest()
