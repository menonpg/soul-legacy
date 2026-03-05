"""
soul-legacy — Polygon blockchain bridge

Connects VaultAnchor.sol to the Python vault.

Testnet: Polygon Amoy  (chain ID 80002) — free, use for testing
Mainnet: Polygon       (chain ID 137)   — real MATIC (~$0.001/tx)

Config in api_keys.json:
  polygon.rpc_url       (Alchemy/Infura endpoint)
  polygon.private_key   (owner wallet — keep secret)
  polygon.contract_addr (deployed VaultAnchor address)
  polygon.network       ("amoy" | "mainnet")
"""

import hashlib, json, os
from pathlib import Path
from typing import Optional


# ── Public RPCs (no API key needed for read-only) ─────────────────────────────
PUBLIC_RPC = {
    "amoy":    "https://rpc-amoy.polygon.technology",
    "mainnet": "https://polygon-rpc.com",
}

CHAIN_ID = {
    "amoy":    80002,
    "mainnet": 137,
}

# Minimal ABI — only what we need
VAULT_ABI = [
    {"name": "register",   "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "vaultHash", "type": "bytes32"}], "outputs": []},
    {"name": "checkin",    "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "newVaultHash", "type": "bytes32"}], "outputs": []},
    {"name": "updateHash", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "newHash", "type": "bytes32"}], "outputs": []},
    {"name": "setGracePeriod", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "days_", "type": "uint256"}], "outputs": []},
    {"name": "release",    "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "owner", "type": "address"}], "outputs": []},
    {"name": "getStatus",  "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}],
     "outputs": [
         {"name": "vaultHash",   "type": "bytes32"},
         {"name": "lastCheckin", "type": "uint256"},
         {"name": "gracePeriod", "type": "uint256"},
         {"name": "released",    "type": "bool"},
         {"name": "canRelease",  "type": "bool"},
         {"name": "releaseAt",   "type": "uint256"},
     ]},
    {"name": "isReleased", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}],
     "outputs": [{"name": "", "type": "bool"}]},
    # Events
    {"name": "Released",  "type": "event",
     "inputs": [{"name": "owner", "type": "address", "indexed": True},
                {"name": "timestamp", "type": "uint256", "indexed": False},
                {"name": "vaultHash", "type": "bytes32", "indexed": False}]},
    {"name": "CheckIn",   "type": "event",
     "inputs": [{"name": "owner", "type": "address", "indexed": True},
                {"name": "timestamp", "type": "uint256", "indexed": False},
                {"name": "vaultHash", "type": "bytes32", "indexed": False}]},
]


# ── Config loader ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    keys_path = os.path.expanduser("~/.openclaw/api_keys.json")
    if os.path.exists(keys_path):
        data = json.load(open(keys_path))
        return data.get("polygon", {})
    return {}


# ── Vault hash ────────────────────────────────────────────────────────────────

def compute_vault_hash(vault) -> bytes:
    """
    SHA256 of all vault records (deterministic, sorted).
    Returns 32 bytes suitable for bytes32 in Solidity.
    """
    records = vault.all_records()
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).digest()


# ── Web3 client ───────────────────────────────────────────────────────────────

class VaultAnchorClient:
    """
    Python client for VaultAnchor.sol on Polygon.

    Usage:
        client = VaultAnchorClient()
        client.register(vault)
        client.checkin(vault)
        status = client.get_status(owner_address)
    """

    def __init__(self, config: dict = None):
        try:
            from web3 import Web3
        except ImportError:
            raise ImportError("Install web3: pip install web3")

        cfg            = config or _load_config()
        self.network   = cfg.get("network", "amoy")
        rpc            = cfg.get("rpc_url") or PUBLIC_RPC[self.network]
        self.w3        = Web3(Web3.HTTPProvider(rpc))
        self.chain_id  = CHAIN_ID[self.network]
        self.account   = None
        self.contract  = None

        pk = cfg.get("private_key")
        if pk:
            self.account = self.w3.eth.account.from_key(pk)

        addr = cfg.get("contract_addr")
        if addr:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(addr),
                abi=VAULT_ABI
            )

    def _send_tx(self, fn):
        """Build, sign, send a transaction."""
        assert self.account, "Private key not configured"
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        tx    = fn.build_transaction({
            "from":     self.account.address,
            "nonce":    nonce,
            "chainId":  self.chain_id,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return {
            "tx_hash":    tx_hash.hex(),
            "block":      receipt.blockNumber,
            "gas_used":   receipt.gasUsed,
            "network":    self.network,
            "explorer":   f"https://{'amoy.' if self.network=='amoy' else ''}polygonscan.com/tx/{tx_hash.hex()}"
        }

    def register(self, vault) -> dict:
        """Register vault on-chain for the first time."""
        vh = compute_vault_hash(vault)
        return self._send_tx(self.contract.functions.register(vh))

    def checkin(self, vault) -> dict:
        """Check in — owner is alive, update vault hash."""
        vh = compute_vault_hash(vault)
        return self._send_tx(self.contract.functions.checkin(vh))

    def update_hash(self, vault) -> dict:
        """Update vault hash after adding/editing records."""
        vh = compute_vault_hash(vault)
        return self._send_tx(self.contract.functions.updateHash(vh))

    def set_grace_period(self, days: int) -> dict:
        return self._send_tx(self.contract.functions.setGracePeriod(days))

    def trigger_release(self, owner_address: str) -> dict:
        """Anyone can call this after grace period expires."""
        return self._send_tx(self.contract.functions.release(owner_address))

    def get_status(self, owner_address: str) -> dict:
        if not self.contract:
            return {"error": "Contract not configured"}
        s = self.contract.functions.getStatus(
            self.w3.eth.account.from_key  # just checksum
            if False else self.w3.to_checksum_address(owner_address)
        ).call()
        return {
            "vault_hash":   s[0].hex(),
            "last_checkin": s[1],
            "grace_period_days": s[2] // 86400,
            "released":     s[3],
            "can_release":  s[4],
            "release_at":   s[5],
            "network":      self.network,
        }

    def watch_release_events(self, owner_address: str, from_block: int = 0):
        """Poll for Release events for this owner."""
        if not self.contract:
            return []
        filt = self.contract.events.Released.create_filter(
            fromBlock=from_block,
            argument_filters={"owner": self.w3.to_checksum_address(owner_address)}
        )
        return filt.get_all_entries()


# ── Convenience functions (used by deadmans.py) ───────────────────────────────

def anchor_checkin(vault) -> Optional[dict]:
    """Called on every owner check-in — updates hash on-chain."""
    try:
        client = VaultAnchorClient()
        return client.checkin(vault)
    except Exception as e:
        return {"error": str(e)}


def anchor_release(vault) -> Optional[dict]:
    """Called when dead man's switch releases — records it on-chain."""
    try:
        client = VaultAnchorClient()
        cfg    = _load_config()
        owner  = cfg.get("owner_address")
        if not owner:
            return {"error": "owner_address not configured"}
        return client.trigger_release(owner)
    except Exception as e:
        return {"error": str(e)}


def anchor_vault_updated(vault) -> Optional[dict]:
    """Call this whenever vault records change — keeps hash current."""
    try:
        client = VaultAnchorClient()
        return client.update_hash(vault)
    except Exception as e:
        return {"error": str(e)}


# ── Auto-detect: local or chain ───────────────────────────────────────────────

def get_anchor(vault):
    """
    Returns LocalAnchor if no Polygon wallet configured,
    VaultAnchorClient if fully configured.
    Swap is seamless — identical API either way.
    """
    cfg = _load_config()
    if cfg.get("private_key") and cfg.get("contract_addr"):
        return VaultAnchorClient(cfg)
    else:
        from .local_anchor import LocalAnchor
        return LocalAnchor(vault)


def anchor_checkin(vault) -> dict:
    return get_anchor(vault).checkin(vault)

def anchor_release(vault) -> dict:
    return get_anchor(vault).trigger_release()

def anchor_vault_updated(vault) -> dict:
    return get_anchor(vault).update_hash(vault)
