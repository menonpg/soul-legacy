"""
soul-legacy — Local Anchor

Mirrors VaultAnchor.sol exactly but stores everything locally.
No wallet, no MATIC, no network required.

When you're ready to go on-chain:
    anchor = LocalAnchor(vault)
    anchor.export_for_chain()   # returns pending records to commit
    # then deploy VaultAnchor.sol and commit them all at once

Local file: vault_dir/anchor.json
"""

import hashlib, json, secrets, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def _ts() -> int:
    return int(time.time())

def _iso(ts: int = None) -> str:
    return datetime.utcfromtimestamp(ts or _ts()).isoformat() + "Z"

def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalAnchor:
    """
    Local simulation of VaultAnchor.sol.

    Identical API to VaultAnchorClient — drop-in replacement.
    All records signed with a local keypair (HMAC-SHA256).
    Pending records can be exported and committed on-chain later.

    State:
        registered     bool
        vault_hash     str (hex)
        last_checkin   int (unix)
        grace_period   int (seconds, default 30 days)
        released       bool
        log            list of signed events
        pending_chain  list of events not yet anchored on-chain
    """

    DEFAULT_GRACE = 30 * 86400   # 30 days in seconds
    RELEASE_DELAY = 7  * 86400   # 7 day extra grace

    def __init__(self, vault):
        self.vault      = vault
        self.path       = Path(vault.dir) / "anchor.json"
        self._secret    = self._load_secret(vault)
        self.state      = self._load()

    def _load_secret(self, vault) -> str:
        """Per-vault HMAC secret — stays local, never leaves vault dir."""
        sp = Path(vault.dir) / ".anchor_secret"
        if not sp.exists():
            sp.write_text(secrets.token_hex(32))
            sp.chmod(0o600)
        return sp.read_text().strip()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "registered":    False,
            "vault_hash":    None,
            "last_checkin":  None,
            "grace_period":  self.DEFAULT_GRACE,
            "released":      False,
            "log":           [],
            "pending_chain": [],
        }

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2))
        self.path.chmod(0o600)

    def _sign(self, event: dict) -> str:
        """HMAC-SHA256 signature — proves event wasn't tampered with."""
        import hmac as _hmac
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        return _hmac.new(
            self._secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def _record(self, event_type: str, data: dict) -> dict:
        event = {
            "type":      event_type,
            "timestamp": _ts(),
            "iso":       _iso(),
            "data":      data,
        }
        event["signature"] = self._sign(event)
        self.state["log"].append(event)
        self.state["pending_chain"].append(event)
        return event

    # ── Mirror VaultAnchor.sol interface ──────────────────────────────────────

    def register(self, vault=None) -> dict:
        v = vault or self.vault
        vh = compute_vault_hash(v)
        self.state["registered"]   = True
        self.state["vault_hash"]   = vh
        self.state["last_checkin"] = _ts()
        self.state["released"]     = False
        event = self._record("Register", {"vault_hash": vh})
        self._save()
        return {"status": "registered", "vault_hash": vh,
                "event": event, "mode": "local"}

    def checkin(self, vault=None) -> dict:
        v  = vault or self.vault
        vh = compute_vault_hash(v)
        assert not self.state["released"], "Vault already released"
        self.state["vault_hash"]   = vh
        self.state["last_checkin"] = _ts()
        event = self._record("CheckIn", {"vault_hash": vh})
        self._save()
        next_due = _iso(self.state["last_checkin"] + self.state["grace_period"])
        return {"status": "ok", "vault_hash": vh,
                "next_due": next_due, "event": event, "mode": "local"}

    def update_hash(self, vault=None) -> dict:
        v  = vault or self.vault
        vh = compute_vault_hash(v)
        self.state["vault_hash"] = vh
        event = self._record("HashUpdate", {"vault_hash": vh})
        self._save()
        return {"vault_hash": vh, "event": event, "mode": "local"}

    def set_grace_period(self, days: int) -> dict:
        assert 7 <= days <= 365, "Grace period must be 7–365 days"
        self.state["grace_period"] = days * 86400
        event = self._record("GracePeriodSet", {"days": days})
        self._save()
        return {"grace_days": days, "event": event, "mode": "local"}

    def trigger_release(self, owner_address: str = None) -> dict:
        s   = self.state
        now = _ts()
        deadline = (s["last_checkin"] or 0) + s["grace_period"] + self.RELEASE_DELAY
        assert now >= deadline, \
            f"Grace period not expired. Releases at {_iso(deadline)}"
        s["released"] = True
        event = self._record("Released", {
            "vault_hash": s["vault_hash"],
            "grace_days": s["grace_period"] // 86400,
        })
        self._save()
        return {"released": True, "event": event, "mode": "local"}

    def get_status(self, owner_address: str = None) -> dict:
        s          = self.state
        now        = _ts()
        last       = s["last_checkin"] or now
        grace      = s["grace_period"]
        release_at = last + grace + self.RELEASE_DELAY
        days_since = (now - last) // 86400
        days_left  = max(0, (grace - (now - last)) // 86400)
        return {
            "registered":        s["registered"],
            "vault_hash":        s["vault_hash"],
            "last_checkin":      _iso(last) if last else None,
            "grace_period_days": grace // 86400,
            "days_since":        days_since,
            "days_left":         days_left,
            "released":          s["released"],
            "can_release":       now >= release_at and not s["released"],
            "release_at":        _iso(release_at),
            "events_logged":     len(s["log"]),
            "pending_chain":     len(s["pending_chain"]),
            "mode":              "local",
            "chain_ready":       False,
        }

    # ── Export for on-chain commit ─────────────────────────────────────────────

    def export_for_chain(self) -> dict:
        """
        Export all pending events for on-chain anchoring.
        Call this when you're ready to deploy VaultAnchor.sol.

        Returns a bundle you can submit to the blockchain in one batch,
        proving the full history of check-ins and vault state.
        """
        bundle = {
            "vault_hash":     self.state["vault_hash"],
            "grace_days":     self.state["grace_period"] // 86400,
            "event_count":    len(self.state["pending_chain"]),
            "events":         self.state["pending_chain"],
            "export_time":    _iso(),
            "instructions": (
                "1. Deploy VaultAnchor.sol to Polygon\n"
                "2. Call register(vault_hash) with the current vault_hash\n"
                "3. Call setGracePeriod(grace_days)\n"
                "4. All historical events are cryptographically signed locally.\n"
                "   Future check-ins will be anchored on-chain automatically."
            )
        }
        return bundle

    def clear_pending(self):
        """Call after successfully anchoring on-chain."""
        self.state["pending_chain"] = []
        self._save()

    def verify_log(self) -> dict:
        """Verify all local event signatures — detect tampering."""
        import hmac as _hmac
        results = []
        for event in self.state["log"]:
            sig   = event.pop("signature", "")
            check = self._sign(event)
            event["signature"] = sig
            results.append({
                "type":  event["type"],
                "time":  event["iso"],
                "valid": _hmac.compare_digest(sig, check),
            })
        tampered = [r for r in results if not r["valid"]]
        return {"total": len(results), "valid": len(results) - len(tampered),
                "tampered": tampered, "integrity": "ok" if not tampered else "COMPROMISED"}


# ── Shared vault hash (used by both local + chain) ────────────────────────────

def compute_vault_hash(vault) -> str:
    records   = vault.all_records()
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
