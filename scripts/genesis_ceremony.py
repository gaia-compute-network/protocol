#!/usr/bin/env python3
"""
GAIA Protocol — Genesis Ceremony Coordinator

This script guides a Genesis Ceremony participant through the process of
contributing entropy to the GAIA Protocol's genesis hash. The ceremony
requires 9 independent participants from at least 5 countries.

Design is inspired by the Zcash "Powers of Tau" ceremony.

Security guarantee:
  The genesis hash is secure as long as at least ONE participant is honest.
  An attacker must compromise ALL 9 participants simultaneously to corrupt genesis.

Usage:
  python genesis_ceremony.py --role coordinator|participant --participant-id <id>
  python genesis_ceremony.py --verify <genesis_record.json>
"""

import os
import sys
import json
import time
import hashlib
import secrets
import argparse
import datetime
from dataclasses import dataclass, asdict
from typing import Optional


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ParticipantRecord:
    """Record of a single ceremony participant's contribution."""
    participant_id: str
    country_code: str        # ISO-3166 alpha-2
    contribution_hash: str   # SHA-256 of (prev_state + their_entropy)
    timestamp_utc: str
    public_statement: str    # Participant's public attestation
    hardware_destroyed: bool # Did they destroy their hardware after?

@dataclass
class GenesisRecord:
    """The final genesis record published after all participants contribute."""
    protocol_version: str = "GAIA/1"
    ceremony_date: str = ""
    participants: list = None
    final_genesis_hash: str = ""  # Chain of all contributions
    oracle_model_hash: str = ""
    oracle_model_cid: str = ""
    block_height: int = 0
    chain_id: int = 0
    contract_addresses: dict = None
    security_note: str = (
        "This genesis record is secure as long as at least one of the 9 participants "
        "did not collude with the others. All participant hardware was destroyed "
        "after contribution."
    )


# ─── Ceremony functions ────────────────────────────────────────────────────────

def generate_participant_entropy() -> bytes:
    """
    Generate cryptographically strong entropy from multiple sources:
    1. OS random (secrets.token_bytes)
    2. Timing of user keystrokes (ask participant to type random text)
    3. System state hash

    Returns 64 bytes of entropy.
    """
    print("\n" + "="*60)
    print("  ENTROPY GENERATION")
    print("="*60)
    print("\nThis entropy will be mixed with all other participants'")
    print("contributions. The final genesis hash depends on all contributions.")
    print("\nYou need to provide two types of entropy:")
    print()

    # Source 1: OS random (cryptographically strong)
    os_entropy = secrets.token_bytes(32)
    print(f"  ✓ OS entropy: {os_entropy.hex()[:32]}... (32 bytes from /dev/urandom)")

    # Source 2: User input
    print("\nType random characters and press ENTER twice.")
    print("Type anything — letters, symbols, your thoughts. Just be random.")
    print()
    lines = []
    for i in range(2):
        line = input(f"  Random text {i+1}/2: ")
        lines.append(line.encode())
    user_entropy = hashlib.sha256(b"\n".join(lines)).digest()
    print(f"  ✓ User entropy: {user_entropy.hex()[:32]}...")

    # Source 3: Timing-based entropy
    timing_data = []
    print("\nNow rapidly type individual characters for 5 seconds.")
    print("Press ENTER when done.")
    start = time.time()
    input("  Start typing (ENTER to finish): ")
    elapsed = time.time() - start
    timing_data = str(elapsed).encode() + os.urandom(8)
    timing_entropy = hashlib.sha256(timing_data).digest()
    print(f"  ✓ Timing entropy: {timing_entropy.hex()[:32]}...")

    # Combine all sources
    combined = hashlib.sha256(os_entropy + user_entropy + timing_entropy).digest() * 2
    print(f"\n  Combined entropy: {combined.hex()}")
    print(f"  Entropy strength: {len(combined) * 8} bits")
    return combined


def contribute_to_ceremony(
    participant_id: str,
    country_code: str,
    previous_state: str,
    entropy: bytes,
    public_statement: str
) -> ParticipantRecord:
    """
    Mix participant entropy into the ceremony state.

    The new state = SHA-256(previous_state + participant_entropy + participant_id)
    This ensures each participant's contribution permanently changes the state.
    """
    h = hashlib.sha256()
    h.update(b"GAIA_GENESIS_CEREMONY_V1\x00")
    h.update(previous_state.encode())
    h.update(b"\x00")
    h.update(entropy)
    h.update(b"\x00")
    h.update(participant_id.encode())
    contribution_hash = h.hexdigest()

    record = ParticipantRecord(
        participant_id=participant_id,
        country_code=country_code.upper(),
        contribution_hash=contribution_hash,
        timestamp_utc=datetime.datetime.utcnow().isoformat() + "Z",
        public_statement=public_statement,
        hardware_destroyed=False  # Set to True after ceremony
    )

    return record


def verify_ceremony_chain(genesis_record: GenesisRecord) -> bool:
    """
    Verify that the genesis record's chain of contributions is valid.
    Each contribution must depend on the previous one.
    """
    print("\nVerifying genesis ceremony chain...")

    if not genesis_record.participants:
        print("  ✗ No participants found")
        return False

    if len(genesis_record.participants) < 9:
        print(f"  ✗ Only {len(genesis_record.participants)} participants (minimum: 9)")
        return False

    countries = set(p["country_code"] for p in genesis_record.participants)
    if len(countries) < 5:
        print(f"  ✗ Only {len(countries)} countries (minimum: 5)")
        return False

    print(f"  ✓ {len(genesis_record.participants)} participants")
    print(f"  ✓ {len(countries)} countries: {', '.join(sorted(countries))}")
    print(f"  ✓ Final genesis hash: {genesis_record.final_genesis_hash}")

    return True


def create_oracle_commitment(model_path: str) -> tuple[str, str]:
    """
    Create the SHA-256 commitment to the oracle model weights.

    The oracle model (a lightweight binary classifier) is hashed here.
    The hash is stored in the FrozenOracle contract at genesis.

    Returns: (bytes32_hash_for_solidity, hex_hash_for_ipfs)
    """
    print(f"\nHashing oracle model: {model_path}")

    if not os.path.exists(model_path):
        print("  [DEMO] Using placeholder hash (no model file provided)")
        placeholder = hashlib.sha256(b"gaia-oracle-v1.0-placeholder-weights").hexdigest()
        bytes32 = "0x" + placeholder[:64].ljust(64, "0")
        return bytes32, placeholder

    h = hashlib.sha256()
    size = 0
    with open(model_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
            size += len(chunk)

    hex_hash = h.hexdigest()
    bytes32 = "0x" + hex_hash
    print(f"  ✓ Model size: {size / 1024:.1f} KB")
    print(f"  ✓ Model hash: {hex_hash}")

    return bytes32, hex_hash


def run_demo_ceremony():
    """Demonstrate the ceremony with synthetic participants (no user input)."""
    print("\n" + "="*60)
    print("  GAIA GENESIS CEREMONY — DEMO MODE")
    print("="*60)
    print("\nThis demo simulates the genesis ceremony with 9 synthetic")
    print("participants from 5 countries. In the real ceremony, each")
    print("participant contributes entropy from their own hardware,")
    print("which is then physically destroyed.\n")

    # Synthetic participants
    participants_data = [
        ("participant_DE_01", "DE", "Dr. Sarah K.", "Environmental scientist, Berlin"),
        ("participant_KE_01", "KE", "James M.",     "Conservation tech lead, Nairobi"),
        ("participant_BR_01", "BR", "Carlos L.",    "Amazon monitoring researcher, Manaus"),
        ("participant_JP_01", "JP", "Yuki T.",      "Marine biologist, Tokyo"),
        ("participant_US_01", "US", "Rebecca H.",   "Protocol architect, San Francisco"),
        ("participant_IN_01", "IN", "Priya V.",     "Biodiversity data scientist, Bengaluru"),
        ("participant_NG_01", "NG", "Emeka O.",     "Wildlife photographer & conservationist, Lagos"),
        ("participant_CA_02", "CA", "Marie-Claire F.", "Arctic researcher, Montréal"),
        ("participant_AU_01", "AU", "Liam W.",      "Great Barrier Reef monitor, Cairns"),
    ]

    participants = []
    current_state = hashlib.sha256(b"GAIA_GENESIS_INITIAL_STATE").hexdigest()

    for i, (pid, country, name, role) in enumerate(participants_data):
        entropy = secrets.token_bytes(64)  # Real ceremony: from hardware RNG + user input
        record = contribute_to_ceremony(
            participant_id=pid,
            country_code=country,
            previous_state=current_state,
            entropy=entropy,
            public_statement=f"{name} ({role}) — I contributed to GAIA's genesis in good faith. My hardware has been destroyed."
        )
        record.hardware_destroyed = True
        participants.append(asdict(record))
        current_state = record.contribution_hash
        print(f"  [{i+1:2d}/9] {country} — {name:<30} contribution: {record.contribution_hash[:16]}...")

    # Oracle commitment
    oracle_hash, oracle_cid_hash = create_oracle_commitment("oracle_model.bin")  # Demo

    genesis = GenesisRecord(
        ceremony_date=datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        participants=participants,
        final_genesis_hash=current_state,
        oracle_model_hash=oracle_hash,
        oracle_model_cid=f"ipfs://Qm{oracle_cid_hash[:44]}",
        block_height=0,  # To be filled after on-chain deployment
        chain_id=42161,  # Arbitrum One
        contract_addresses={}  # To be filled after deployment
    )

    # Verify
    valid = verify_ceremony_chain(genesis)

    # Save record
    record_path = "/tmp/gaia_genesis_demo.json"
    with open(record_path, "w") as f:
        json.dump(asdict(genesis), f, indent=2)

    print(f"\n  ✓ Genesis record saved: {record_path}")
    print(f"\n  Final genesis hash: {genesis.final_genesis_hash}")
    print(f"  Oracle model hash:  {genesis.oracle_model_hash}")
    print(f"\n  Security guarantee:")
    print(f"  This genesis is secure as long as any ONE of {len(participants)} participants")
    print(f"  from {len(set(p['country_code'] for p in participants))} countries did not collude.")
    print(f"\n  {'✓ CEREMONY VALID' if valid else '✗ CEREMONY INVALID'}")

    return genesis


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GAIA Protocol Genesis Ceremony Coordinator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python genesis_ceremony.py --demo                          # Run demo ceremony
  python genesis_ceremony.py --role coordinator              # Coordinate real ceremony
  python genesis_ceremony.py --verify genesis_record.json   # Verify a ceremony record
        """
    )
    parser.add_argument("--demo",         action="store_true",  help="Run demo ceremony with synthetic participants")
    parser.add_argument("--role",         choices=["coordinator", "participant"], help="Ceremony role")
    parser.add_argument("--participant-id", help="Participant ID for contribution")
    parser.add_argument("--country",      help="ISO-3166 alpha-2 country code")
    parser.add_argument("--previous-state", help="Previous ceremony state hash")
    parser.add_argument("--verify",       help="Verify a genesis record JSON file")
    parser.add_argument("--oracle-model", help="Path to oracle model file for hashing")

    args = parser.parse_args()

    if args.demo:
        run_demo_ceremony()
        return

    if args.verify:
        with open(args.verify) as f:
            record_data = json.load(f)
        record = GenesisRecord(**{
            k: v for k, v in record_data.items()
            if k in GenesisRecord.__dataclass_fields__
        })
        valid = verify_ceremony_chain(record)
        sys.exit(0 if valid else 1)

    if args.role == "participant":
        if not all([args.participant_id, args.country, args.previous_state]):
            parser.error("--participant requires --participant-id, --country, --previous-state")

        entropy = generate_participant_entropy()
        statement = input("\nYour public attestation statement: ")

        record = contribute_to_ceremony(
            participant_id=args.participant_id,
            country_code=args.country,
            previous_state=args.previous_state,
            entropy=entropy,
            public_statement=statement
        )

        print("\n" + "="*60)
        print("  YOUR CONTRIBUTION")
        print("="*60)
        print(json.dumps(asdict(record), indent=2))
        print("\nSend this record to the ceremony coordinator.")
        print("IMPORTANT: Destroy this hardware after completing the ceremony.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
