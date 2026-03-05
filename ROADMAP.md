# Soul Legacy — Roadmap

## v0.1.0 (current)
- [x] 8-section encrypted vault (AES-256)
- [x] CLI: init, add, list, show, ingest, search, chat, soul-chat, serve
- [x] RAG + RLM + Darwin advisor (soul.py v2.0)
- [x] Web UI (FastAPI + vanilla SPA)
- [x] Local mode (passphrase) + Cloud mode (JWT + accounts)
- [x] Dead man's switch (time-based, email + in-app check-in)
- [x] Scoped access tokens per inheritor (role-based: executor/attorney/accountant/family)
- [x] Blockchain anchoring — VaultAnchor.sol on Polygon Amoy testnet
- [x] Railway deployment

## v0.2.0
- [ ] M-of-N trustee signing for early release
      "2 of 3 trustees must agree before vault releases"
- [ ] SMS check-in (Twilio) in addition to email
- [ ] Inheritor portal — scoped read-only web UI for each inheritor
- [ ] Vault diff — show what changed since last blockchain anchor
- [ ] Dead man's switch widget in web UI (countdown timer, check-in button)

## v0.3.0
- [ ] Death certificate oracle
      Trusted third party (attorney, notary) can trigger release
      Removes "waiting game" — release on proof of death, not just time
- [ ] Conditional unlock smart contract
      "Release assets section to executor ONLY after probate filing"
      "Release digital assets to family after 6 months"
- [ ] Multi-sig wallet integration (Gnosis Safe)

## v0.4.0 (Enterprise / Family)
- [ ] Family vault — shared access across multiple owners
- [ ] Attorney dashboard — manage multiple client vaults
- [ ] HIPAA-ready mode (healthcare directives, medical records)
- [ ] White-label for estate attorneys / financial advisors

## Future
- [ ] Polygon mainnet deployment (after testnet validation)
- [ ] IPFS document storage (decentralized, censorship-resistant)
- [ ] Zero-knowledge proofs — prove vault integrity without revealing contents
- [ ] soul.py soul-book integration — narrative life story alongside legal estate
