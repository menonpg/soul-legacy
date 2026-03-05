// SPDX-License-Identifier: BSL-1.1
pragma solidity ^0.8.20;

/**
 * VaultAnchor.sol — Soul Legacy Dead Man's Switch
 *
 * Deployed on Polygon (Amoy testnet → mainnet).
 *
 * What it does:
 *   - Owner checks in periodically (resets the clock)
 *   - If no check-in within gracePeriod days → anyone can trigger release
 *   - Release emits an event → off-chain server grants inheritor access
 *   - Vault hash stored on-chain → proves contents haven't been tampered with
 *
 * Roadmap (not yet implemented):
 *   - M-of-N trustee signing for early release
 *   - Conditional unlock (death certificate oracle)
 *   - Multi-vault family accounts
 */
contract VaultAnchor {

    // ── Events ────────────────────────────────────────────────────────────────

    event CheckIn(address indexed owner, uint256 timestamp, bytes32 vaultHash);
    event Released(address indexed owner, uint256 timestamp, bytes32 vaultHash);
    event GracePeriodUpdated(address indexed owner, uint256 newGraceDays);
    event VaultHashUpdated(address indexed owner, bytes32 newHash);

    // ── State ─────────────────────────────────────────────────────────────────

    struct Vault {
        address owner;
        bytes32 vaultHash;       // SHA256 of vault contents (set off-chain)
        uint256 lastCheckin;     // unix timestamp
        uint256 gracePeriod;     // seconds (default: 30 days)
        bool    released;
        bool    exists;
    }

    mapping(address => Vault) public vaults;

    uint256 public constant DEFAULT_GRACE = 30 days;
    uint256 public constant RELEASE_DELAY = 7  days;  // extra grace after warning

    // ── Register ──────────────────────────────────────────────────────────────

    function register(bytes32 vaultHash) external {
        require(!vaults[msg.sender].exists, "Already registered");
        vaults[msg.sender] = Vault({
            owner:       msg.sender,
            vaultHash:   vaultHash,
            lastCheckin: block.timestamp,
            gracePeriod: DEFAULT_GRACE,
            released:    false,
            exists:      true
        });
        emit CheckIn(msg.sender, block.timestamp, vaultHash);
    }

    // ── Check in (owner is alive) ─────────────────────────────────────────────

    function checkin(bytes32 newVaultHash) external {
        Vault storage v = vaults[msg.sender];
        require(v.exists,    "Vault not registered");
        require(!v.released, "Vault already released");
        v.lastCheckin = block.timestamp;
        v.vaultHash   = newVaultHash;
        emit CheckIn(msg.sender, block.timestamp, newVaultHash);
    }

    // ── Update vault hash (after adding records) ──────────────────────────────

    function updateHash(bytes32 newHash) external {
        Vault storage v = vaults[msg.sender];
        require(v.exists && !v.released, "Not active");
        v.vaultHash = newHash;
        emit VaultHashUpdated(msg.sender, newHash);
    }

    // ── Set grace period ──────────────────────────────────────────────────────

    function setGracePeriod(uint256 days_) external {
        require(days_ >= 7 && days_ <= 365, "Must be 7-365 days");
        Vault storage v = vaults[msg.sender];
        require(v.exists && !v.released, "Not active");
        v.gracePeriod = days_ * 1 days;
        emit GracePeriodUpdated(msg.sender, days_);
    }

    // ── Release (anyone can call after grace + delay expired) ─────────────────

    function release(address owner) external {
        Vault storage v = vaults[owner];
        require(v.exists,    "Vault not registered");
        require(!v.released, "Already released");
        require(
            block.timestamp >= v.lastCheckin + v.gracePeriod + RELEASE_DELAY,
            "Grace period not expired"
        );
        v.released = true;
        emit Released(owner, block.timestamp, v.vaultHash);
    }

    // ── View ──────────────────────────────────────────────────────────────────

    function getStatus(address owner) external view returns (
        bytes32 vaultHash,
        uint256 lastCheckin,
        uint256 gracePeriod,
        bool    released,
        bool    canRelease,
        uint256 releaseAt
    ) {
        Vault storage v = vaults[owner];
        uint256 _releaseAt = v.lastCheckin + v.gracePeriod + RELEASE_DELAY;
        return (
            v.vaultHash,
            v.lastCheckin,
            v.gracePeriod,
            v.released,
            block.timestamp >= _releaseAt,
            _releaseAt
        );
    }

    function isReleased(address owner) external view returns (bool) {
        return vaults[owner].released;
    }
}
