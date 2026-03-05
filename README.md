# 🏛️ soul-legacy

> *Your life, documented. Your wishes, honored.*

**soul-legacy** is a local-first, encrypted digital estate vault with LLM chat. It's the estate and legacy module of the [soul.py](https://github.com/menonpg/soul.py) ecosystem.

Store everything that matters — assets, insurance, wills, debts, beneficiary designations — encrypted on your own device or in our managed cloud. Ask questions about your estate in plain English. Give your family a clear path forward.

## Why

When someone dies, their family spends months hunting for documents. Most of it is in paper, scattered across files, lawyers, and email. **soul-legacy fixes that.**

## Quick Start

```bash
pip install soul-legacy
soul-legacy init
```

That's it. A guided wizard walks you through setup.

## What It Stores

| Section | What |
|---------|------|
| `assets` | Bank accounts, brokerage, real estate, vehicles, crypto |
| `insurance` | Life, health, property, auto policies |
| `legal` | Will, trust, power of attorney, healthcare directive |
| `debts` | Mortgage, loans, credit cards |
| `contacts` | Attorney, accountant, executor, advisors |
| `beneficiaries` | Who gets what |
| `digital` | Email, social media, crypto wallets |
| `wishes` | Funeral, medical, personal messages |

## Commands

```bash
soul-legacy init                    # create vault (guided)
soul-legacy add assets              # add an asset
soul-legacy list assets             # list all assets
soul-legacy show assets <id>        # view a record
soul-legacy chat                    # ask questions in plain English
soul-legacy summary                 # full estate overview
soul-legacy status                  # vault health + fingerprint
```

## Chat Examples

```
You: What life insurance policies do I have?
You: Who are my beneficiaries?
You: What debts would my estate need to settle?
You: Generate a checklist for my executor
You: What's my estimated net worth?
```

## Security Model

- **Zero-knowledge encryption** — AES-128 + HMAC-SHA256, key never leaves device
- **PBKDF2-SHA256** key derivation, 600,000 iterations (OWASP 2023)
- **GitHub storage** — repo contains only ciphertext
- **Blockchain anchoring** — vault hash committed to Polygon (optional)
- **Open source** — audit the encryption yourself

**If you lose your passphrase, your data is unrecoverable. Store it safely.**

## Storage Options

| Mode | Command | Cost |
|------|---------|------|
| Local only | `soul-legacy init` | Free |
| GitHub backup | `soul-legacy init --github` | Free |
| Managed cloud | `soul-legacy init --cloud` | $9-29/mo |

## Part of the soul.py Ecosystem

```
soul.py        →  who you are (identity, memory, values)
soul-legacy    →  what you have (assets, wishes, legacy)
soul-schema    →  data layer
soulmate       →  enterprise memory
```

## License

BSL 1.1 — free for personal use. Contact us for commercial licensing.
Source available. Converts to MIT on 2030-03-05.

---

Built by [The Menon Lab](https://themenonlab.com)
