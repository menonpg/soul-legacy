"""
soul-legacy — Dead Man's Switch

Flow:
  Owner checks in periodically (email link or in-app button)
  If no check-in within grace_days:
    Day grace-3 → warning email
    Day grace   → final warning + SMS (if configured)
    Day grace+7 → release: inheritors get scoped access tokens + emails

Config stored in vault meta:
  deadmans.grace_days       (default: 30)
  deadmans.last_checkin     (ISO timestamp)
  deadmans.status           (active | warned | released | paused)
  deadmans.warning_sent_at  (ISO timestamp)
  deadmans.released_at      (ISO timestamp)
  deadmans.inheritors       (list of {name, email, sections, role})
"""

import os, json, secrets, hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.utcnow()

def _iso(dt: datetime) -> str:
    return dt.isoformat() + "Z"

def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s.rstrip("Z"))


# ── DeadMansSwitch ────────────────────────────────────────────────────────────

class DeadMansSwitch:
    """
    Manages the dead man's switch for a vault.

    Usage:
        dms = DeadMansSwitch(vault)
        dms.setup(grace_days=30, inheritors=[...])
        dms.checkin()           # owner is alive
        dms.tick()              # call this daily (cron) to check state
        dms.status()            # current state
    """

    def __init__(self, vault):
        self.vault    = vault
        self.cfg_path = Path(vault.dir) / "deadmans.json"
        self.cfg      = self._load()

    def _load(self) -> dict:
        if self.cfg_path.exists():
            return json.loads(self.cfg_path.read_text())
        return {
            "grace_days":      30,
            "last_checkin":    _iso(_now()),
            "status":          "active",
            "warning_sent_at": None,
            "released_at":     None,
            "inheritors":      [],
            "checkin_token":   secrets.token_urlsafe(32),
        }

    def _save(self):
        self.cfg_path.write_text(json.dumps(self.cfg, indent=2))
        self.cfg_path.chmod(0o600)

    def setup(self, grace_days: int = 30, inheritors: list = None):
        """
        Configure the dead man's switch.

        inheritors: list of dicts:
          { name, email, role, sections }
          role:     executor | attorney | accountant | family | inheritor
          sections: ["assets","insurance",...] or ["all"]
        """
        self.cfg["grace_days"]  = grace_days
        self.cfg["last_checkin"] = _iso(_now())
        self.cfg["status"]       = "active"
        if inheritors:
            self.cfg["inheritors"] = inheritors
        self._save()
        return self.cfg

    def checkin(self) -> dict:
        """Owner is alive — reset the clock."""
        self.cfg["last_checkin"] = _iso(_now())
        self.cfg["status"]       = "active"
        self.cfg["warning_sent_at"] = None
        self.cfg["checkin_token"]   = secrets.token_urlsafe(32)  # rotate token
        self._save()
        return {"status": "ok", "next_due": _iso(
            _parse(self.cfg["last_checkin"]) + timedelta(days=self.cfg["grace_days"])
        )}

    def checkin_by_token(self, token: str) -> bool:
        """Validate email link check-in token."""
        if secrets.compare_digest(token, self.cfg.get("checkin_token", "")):
            self.checkin()
            return True
        return False

    def status(self) -> dict:
        last   = _parse(self.cfg["last_checkin"])
        grace  = self.cfg["grace_days"]
        now    = _now()
        days_since   = (now - last).days
        days_left    = grace - days_since
        release_date = last + timedelta(days=grace + 7)
        return {
            "status":       self.cfg["status"],
            "last_checkin": self.cfg["last_checkin"],
            "grace_days":   grace,
            "days_since":   days_since,
            "days_left":    max(0, days_left),
            "release_date": _iso(release_date),
            "inheritors":   len(self.cfg.get("inheritors", [])),
            "checkin_url":  f"/api/checkin/{self.cfg['checkin_token']}",
        }

    def tick(self, resend_key: str = None, base_url: str = "") -> dict:
        """
        Call daily. Checks state and fires warnings/release as needed.
        Returns action taken.
        """
        if self.cfg["status"] in ("released", "paused"):
            return {"action": "none", "status": self.cfg["status"]}

        last       = _parse(self.cfg["last_checkin"])
        grace      = self.cfg["grace_days"]
        now        = _now()
        days_since = (now - last).days

        # Warning: 3 days before grace expires
        if days_since >= (grace - 3) and not self.cfg.get("warning_sent_at"):
            self._send_warning(resend_key, base_url, days_left=grace-days_since)
            self.cfg["warning_sent_at"] = _iso(now)
            self.cfg["status"] = "warned"
            self._save()
            return {"action": "warning_sent", "days_left": grace - days_since}

        # Release: grace + 7 day final grace expired
        if days_since >= (grace + 7):
            result = self._release(resend_key, base_url)
            self.cfg["status"]      = "released"
            self.cfg["released_at"] = _iso(now)
            self._save()
            return {"action": "released", **result}

        return {"action": "none", "days_since": days_since, "days_left": grace - days_since}

    def _send_warning(self, resend_key: str, base_url: str, days_left: int):
        """Send warning email to vault owner."""
        if not resend_key:
            return
        meta       = self.vault.meta()
        owner_name  = meta.get("owner_name", "Vault Owner")
        owner_email = meta.get("owner_email", "")
        if not owner_email:
            return

        checkin_url = f"{base_url}/api/checkin/{self.cfg['checkin_token']}"
        _send_email(resend_key,
            to       = owner_email,
            subject  = f"⚠️ Soul Legacy: Check in within {days_left} days",
            html     = f"""
            <p>Hi {owner_name},</p>
            <p>Your Soul Legacy vault hasn't received a check-in in a while.</p>
            <p><strong>You have {days_left} days before your vault access is released to your designated inheritors.</strong></p>
            <p><a href="{checkin_url}" style="background:#7c6ef0;color:#fff;padding:12px 24px;
               border-radius:8px;text-decoration:none;font-weight:bold">
               ✅ I'm Alive — Check In Now</a></p>
            <p style="color:#888;font-size:12px">
               If you no longer wish to use Soul Legacy, you can pause or disable
               the dead man's switch from your vault settings.</p>
            """)

    def _release(self, resend_key: str, base_url: str) -> dict:
        """Release vault — generate scoped tokens, email inheritors."""
        results = []
        for inheritor in self.cfg.get("inheritors", []):
            token   = _generate_scoped_token(inheritor)
            sections = inheritor.get("sections", ["all"])
            _save_scoped_token(self.vault, token, inheritor, sections)

            if resend_key and inheritor.get("email"):
                _send_email(resend_key,
                    to       = inheritor["email"],
                    subject  = "Soul Legacy: You've been granted vault access",
                    html     = _inheritor_email(inheritor, token, base_url, sections))
            results.append({"name": inheritor["name"], "role": inheritor.get("role"),
                             "sections": sections, "token_issued": True})

        # Try blockchain anchor
        try:
            from .blockchain import anchor_release
            tx = anchor_release(self.vault)
            return {"inheritors_notified": results, "blockchain_tx": tx}
        except Exception as e:
            return {"inheritors_notified": results, "blockchain_tx": None,
                    "blockchain_error": str(e)}

    def pause(self):
        self.cfg["status"] = "paused"
        self._save()

    def resume(self):
        self.cfg["status"] = "active"
        self.cfg["last_checkin"] = _iso(_now())
        self._save()


# ── Scoped access tokens ──────────────────────────────────────────────────────

def _generate_scoped_token(inheritor: dict) -> str:
    base  = f"{inheritor['email']}:{inheritor.get('role','inheritor')}:{secrets.token_hex(16)}"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def _save_scoped_token(vault, token: str, inheritor: dict, sections: list):
    tokens_path = Path(vault.dir) / "access_tokens.json"
    tokens = json.loads(tokens_path.read_text()) if tokens_path.exists() else {}
    tokens[token] = {
        "name":     inheritor["name"],
        "email":    inheritor["email"],
        "role":     inheritor.get("role", "inheritor"),
        "sections": sections,
        "issued_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(days=90)),  # 90 day window
    }
    tokens_path.write_text(json.dumps(tokens, indent=2))
    tokens_path.chmod(0o600)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(resend_key: str, to: str, subject: str, html: str):
    import requests
    requests.post("https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {resend_key}",
                 "Content-Type": "application/json"},
        json={"from": "noreply@themenonlab.com", "to": [to],
              "subject": subject, "html": html}, timeout=10)


def _inheritor_email(inheritor: dict, token: str, base_url: str, sections: list) -> str:
    name     = inheritor["name"]
    role     = inheritor.get("role", "inheritor").title()
    sec_list = ", ".join(sections) if sections != ["all"] else "full vault"
    access_url = f"{base_url}/access/{token}"
    return f"""
    <p>Dear {name},</p>
    <p>You have been designated as a <strong>{role}</strong> in this estate vault.</p>
    <p>You now have access to: <strong>{sec_list}</strong></p>
    <p><a href="{access_url}" style="background:#7c6ef0;color:#fff;padding:12px 24px;
       border-radius:8px;text-decoration:none;font-weight:bold">
       Access Estate Vault</a></p>
    <p style="color:#888;font-size:12px">
       This link is valid for 90 days. Your access is read-only and scoped
       to the sections designated in the estate plan.<br>
       Powered by Soul Legacy · ThinkCreate.AI</p>
    """
