"""
Core vault operations — read/write/list sections.
Everything written to disk is encrypted. Decrypted only in memory.
"""
import os, json
from datetime import datetime
from typing import Optional
from .crypto import encrypt, decrypt, generate_salt, vault_fingerprint


SECTIONS = ["assets", "insurance", "legal", "debts", "contacts",
            "beneficiaries", "digital", "wishes"]


class Vault:
    def __init__(self, vault_dir: str, passphrase: str):
        self.dir        = os.path.expanduser(vault_dir)
        self.passphrase = passphrase
        self._salt_path = os.path.join(self.dir, ".salt")
        self._meta_path = os.path.join(self.dir, "meta.enc")

        if os.path.exists(self._salt_path):
            self.salt = open(self._salt_path, "rb").read()
        else:
            self.salt = None

    def init(self, owner_name: str, owner_email: str = ""):
        os.makedirs(self.dir, exist_ok=True)
        for section in SECTIONS:
            os.makedirs(os.path.join(self.dir, section), exist_ok=True)

        self.salt = generate_salt()
        open(self._salt_path, "wb").write(self.salt)
        os.chmod(self._salt_path, 0o600)

        meta = {
            "owner_name":  owner_name,
            "owner_email": owner_email,
            "created_at":  datetime.now().isoformat(),
            "updated_at":  datetime.now().isoformat(),
            "version":     "0.1.0",
            "storage":     "local",
            "blockchain_anchored": False,
        }
        self._write_enc("meta", json.dumps(meta))
        return meta

    def _section_path(self, section: str, record_id: str) -> str:
        return os.path.join(self.dir, section, f"{record_id}.enc")

    def _write_enc(self, name: str, data: str):
        if name == "meta":
            path = self._meta_path
        else:
            path = name
        token = encrypt(data, self.passphrase, self.salt)
        open(path, "wb").write(token)

    def _read_enc(self, path: str) -> str:
        return decrypt(open(path, "rb").read(), self.passphrase, self.salt)

    def write(self, section: str, record_id: str, data: dict):
        assert section in SECTIONS, f"Unknown section: {section}"
        path  = self._section_path(section, record_id)
        token = encrypt(json.dumps(data), self.passphrase, self.salt)
        open(path, "wb").write(token)
        self._touch_meta()

    def read(self, section: str, record_id: str) -> dict:
        path = self._section_path(section, record_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"{section}/{record_id} not found")
        return json.loads(self._read_enc(path))

    def list(self, section: str) -> list:
        d = os.path.join(self.dir, section)
        return [f.replace(".enc", "") for f in os.listdir(d) if f.endswith(".enc")]

    def delete(self, section: str, record_id: str):
        path = self._section_path(section, record_id)
        if os.path.exists(path):
            os.remove(path)

    def meta(self) -> dict:
        return json.loads(self._read_enc(self._meta_path))

    def all_records(self) -> dict:
        """Decrypt everything into memory — used for LLM context"""
        result = {}
        for section in SECTIONS:
            result[section] = []
            for rid in self.list(section):
                try:
                    result[section].append(self.read(section, rid))
                except:
                    pass
        return result

    def fingerprint(self) -> str:
        return vault_fingerprint(self.dir)

    def _touch_meta(self):
        try:
            m = self.meta()
            m["updated_at"] = datetime.now().isoformat()
            self._write_enc("meta", json.dumps(m))
        except:
            pass

    def verify_passphrase(self) -> bool:
        try:
            self.meta()
            return True
        except:
            return False
