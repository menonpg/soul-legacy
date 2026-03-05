# Monica Handoff — soul-legacy v0.1.0

Hey Monica! Here's everything you need to test, fix, publish, and deploy soul-legacy.

## What is this?

An encrypted digital estate vault with:
- 8 sections (assets, insurance, legal, debts, contacts, beneficiaries, digital, final wishes)
- AI advisor powered by soul.py v2.0 (RAG + RLM + Darwin)
- Dead man's switch with email alerts + scoped inheritor access
- Local blockchain anchor (cryptographic proofs, no wallet needed yet)
- Full web UI (FastAPI + vanilla JS SPA)
- Two modes: local (passphrase) and cloud (multi-tenant, Railway)

---

## Step 1 — Install & Fix

```bash
git clone https://github.com/menonpg/soul-legacy
cd soul-legacy
pip install -e ".[all]"
```

**Known issue:** `cryptography` package fails on ARM/Termux.
On proper Linux it should be fine — if not, fix options:
- `pip install cryptography --only-binary=:all:`
- Or swap Fernet for PyNaCl in `soul_legacy/crypto.py`

---

## Step 2 — Test Locally

```bash
# 1. Init a test vault
soul-legacy init --name "Test User" --email test@example.com
# → prompts for passphrase, creates ~/.soul-legacy/vault/

# 2. Add a record
soul-legacy add assets
# → interactive prompts

# 3. List it
soul-legacy list assets

# 4. Start the web UI (local mode)
soul-legacy serve
# → open http://localhost:8080
# → enter passphrase, explore all sections

# 5. Test chat (needs ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
soul-legacy soul-chat
# → try "what assets do I have?" (RAG)
# → try "summarize everything" (RLM)

# 6. Test dead man's switch
soul-legacy dms setup --grace-days 30
soul-legacy dms status
soul-legacy dms checkin

# 7. Test document ingest (needs a PDF)
soul-legacy ingest ~/some_document.pdf --azure
# or without Azure:
soul-legacy ingest ~/some_document.pdf
```

Fix whatever breaks. There will be bugs — this hasn't been run end-to-end yet.

---

## Step 3 — PyPI Publish

```bash
# Bump version in pyproject.toml if needed (currently 0.1.0)
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions will auto-publish to PyPI via `.github/workflows/publish.yml`.
PyPI token is already set as `PYPI_TOKEN` secret on the repo.

If the workflow doesn't exist yet, create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install build twine
      - run: python -m build
      - run: twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
```

---

## Step 4 — Railway Deploy

1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select `menonpg/soul-legacy` (private repo — make sure Railway has access)
3. Set these environment variables:

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | (ask Prahlad — in his api_keys.json) |
| `SECRET_KEY` | any random 32-char string |
| `PORT` | Railway sets this automatically |
| `SOUL_LEGACY_MODE` | `cloud` |

4. Railway will auto-detect `Procfile` and run:
   ```
   soul-legacy serve --host 0.0.0.0 --port $PORT --cloud
   ```
5. Note the Railway URL (e.g. `soul-legacy-production.up.railway.app`)
6. Report back the URL so Prahlad can set custom domain `legacy.thinkcreateai.com`

---

## Step 5 — Custom Domain (Prahlad handles DNS, you handle Railway)

In Railway project → Settings → Networking → Custom Domain:
- Add: `legacy.thinkcreateai.com`
- Railway will give you a CNAME value to add in GoDaddy
- Report that CNAME value back to Prahlad

---

## Architecture Quick Reference

```
soul_legacy/
  vault.py          — AES-256 encryption, 8 sections
  crypto.py         — Fernet key derivation (PBKDF2)
  deadmans.py       — Dead man's switch, scoped tokens, Resend emails
  local_anchor.py   — Local blockchain (HMAC-signed, no wallet needed)
  blockchain.py     — Polygon bridge (auto-falls back to local_anchor)
  soul_integration.py — soul.py v2.0: RAG + RLM + Darwin + Memory
  ingest.py         — PDF/image/DOCX → extract → embed → vectorstore
  embeddings.py     — fastembed (local) or Azure OpenAI
  vectorstore.py    — SQLite-vec or cosine fallback
  chat.py           — basic RAG chat
  cli.py            — Click CLI entry point
  server/
    app.py          — FastAPI app
    auth.py         — passphrase (local) + JWT (cloud)
    api/
      vault.py      — CRUD for all 8 sections
      chat.py       — RAG + RLM chat endpoint
      ingest.py     — document upload
      deadmans.py   — dead man's switch endpoints
    static/
      index.html    — full SPA (vanilla JS, no build step)

contracts/
  VaultAnchor.sol   — Polygon smart contract (deploy when ready)

docs/
  index.html        — landing page (legacy.thinkcreateai.com)
  CNAME             — legacy.thinkcreateai.com
```

---

## What NOT to do

- Don't change the license (BSL 1.1 — converts to MIT 2030-03-04)
- Don't push any API keys or private keys to the repo
- Don't add PyTorch or GPU dependencies — must stay CPU-only, ARM-safe
- Don't nest other repos inside soul-legacy/

---

## Questions?

Ask Prahlad. He's on Telegram.
