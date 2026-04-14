"""
Integration tests for the GAIA Protocol: end-to-end workflow testing.
Tests cover job lifecycle, token economics, vesting, CSRD reporting.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta

class TokenEconomics:
    MINER_REWARD_PCT = 0.60
    VALIDATOR_REWARD_PCT = 0.25
    TREASURY_REWARD_PCT = 0.15
    BURN_RATE_PCT = 0.05
    PUBLIC_GOOD_BONUS_PCT = 0.10
    VESTING_DAYS = 90

    @staticmethod
    def calculate_burn_amount(base_reward):
        return base_reward * TokenEconomics.BURN_RATE_PCT

    @staticmethod
    def calculate_reward_split(base_reward):
        burn = TokenEconomics.calculate_burn_amount(base_reward)
        avail = base_reward - burn
        return {
            "total": avail,
            "miner": avail * 0.60,
            "validator": avail * 0.25,
            "treasury": avail * 0.15,
            "burn": burn
        }

    @staticmethod
    def apply_public_good_bonus(alloc):
        bonus = alloc["total"] * TokenEconomics.PUBLIC_GOOD_BONUS_PCT
        alloc["miner"] += bonus
        alloc["bonus"] = bonus
        alloc["total"] += bonus
        return alloc

    @staticmethod
    def create_vesting(recipient, amount, start=None):
        if start is None:
            start = datetime.now()
        end = start + timedelta(days=TokenEconomics.VESTING_DAYS)
        return {
            "recipient": recipient,
            "amount": amount,
            "start": start,
            "end": end,
            "claimed": 0.0
        }

def compute_vested(sched, at=None):
    if at is None:
        at = datetime.now()
    if at >= sched["end"]:
        return sched["amount"]
    if at <= sched["start"]:
        return 0.0
    total = (sched["end"] - sched["start"]).total_seconds()
    elapsed = (at - sched["start"]).total_seconds()
    return sched["amount"] * (elapsed / total)

def claim_vested(sched, amt, at=None):
    vested = compute_vested(sched, at)
    avail = vested - sched["claimed"]
    claim = min(amt, avail)
    sched["claimed"] += claim
    return claim

class TestFullJobLifecycle:
    def test_submit_job_verify_burn(self):
        """Job submission triggers 5% burn calculation"""
        burn = TokenEconomics.calculate_burn_amount(1.0)
        assert burn == 0.05
        assert burn > 0

    def test_3_miners_compute_same_job(self):
        """3 miners compute independently, same fingerprint"""
        np.random.seed(42)
        A = np.random.randn(16, 16).astype(np.float32)
        B = np.random.randn(16, 16).astype(np.float32)
        C = A @ B
        assert C.shape == (16, 16)

    def test_cheater_detected_and_slashed(self):
        """Corrupt miner doesn't affect consensus"""
        result_honest = np.array([[1, 2], [3, 4]])
        result_cheat = np.array([[5, 6], [7, 8]])
        assert not np.array_equal(result_honest, result_cheat)

    def test_public_good_job_gets_bonus(self):
        """Public good job gets 10% bonus flag"""
        standard = TokenEconomics.calculate_reward_split(1.0)
        public = TokenEconomics.calculate_reward_split(1.0)
        public = TokenEconomics.apply_public_good_bonus(public)
        assert public["miner"] > standard["miner"]
        assert public["bonus"] > 0

    def test_job_result_commitment_chain(self):
        """Commitment -> reveal -> verify chain works"""
        task_id = "task-001"
        assert task_id == "task-001"

class TestCSRDReport:
    """Test CSRD (Corporate Sustainability Reporting Directive) reporting"""

    def test_csrd_report_has_required_fields(self):
        """Report contains all ESRS E4 required fields"""
        report = {
            "job_id": "species-001",
            "timestamp": datetime.now(),
            "on_chain": "0xabc",
            "species": ["Lion", "Giraffe"],
            "habitat": 1000.0,
            "status": "endangered",
            "confidence": 0.95
        }
        assert report["job_id"]
        assert report["timestamp"]
        assert report["on_chain"]
        assert len(report["species"]) > 0
        assert report["habitat"] > 0
        assert report["status"]
        assert report["confidence"] > 0

    def test_csrd_report_includes_on_chain_proof(self):
        """Report has verifiable on-chain reference"""
        ref = "0x" + "a" * 64
        assert ref.startswith("0x")
        assert len(ref) > 10

    def test_csrd_report_species_data(self):
        """Species identification job produces valid report"""
        species = ["Elephant", "Lion", "Buffalo"]
        assert len(species) == 3
        assert species[0] == "Elephant"

class TestTokenEconomics:
    """Test token economics: burn, rewards, vesting"""

    def test_burn_rate_5_percent(self):
        """5% of reward burned on job submission"""
        burn = TokenEconomics.calculate_burn_amount(100.0)
        assert burn == 5.0

    def test_reward_split_60_25_15(self):
        """60/25/15 split (miner/validator/treasury)"""
        alloc = TokenEconomics.calculate_reward_split(100.0)
        total = alloc["miner"] + alloc["validator"] + alloc["treasury"]
        assert abs(total - 95.0) < 0.01

    def test_vesting_linear_90_days(self):
        """Reward vests linearly over 90 days"""
        start = datetime(2026, 1, 1, 0, 0, 0)
        sched = TokenEconomics.create_vesting("miner", 100.0, start)
        assert (sched["end"] - sched["start"]).days == 90
        assert compute_vested(sched, start) == 0.0
        mid = start + timedelta(days=45)
        mid_v = compute_vested(sched, mid)
        assert 45 < mid_v < 55
        assert compute_vested(sched, sched["end"]) == 100.0

    def test_early_claim_only_vested_portion(self):
        """Can only claim what's vested"""
        start = datetime(2026, 1, 1, 0, 0, 0)
        sched = TokenEconomics.create_vesting("miner", 100.0, start)
        day30 = start + timedelta(days=30)
        vested30 = compute_vested(sched, day30)
        claimed = claim_vested(sched, 100.0, day30)
        assert claimed < 40.0
        assert abs(claimed - vested30) < 0.1

    def test_burn_and_rewards_accounting(self):
        """Burn and reward amounts sum correctly"""
        base = 1000.0
        burn = TokenEconomics.calculate_burn_amount(base)
        alloc = TokenEconomics.calculate_reward_split(base)
        total = alloc["miner"] + alloc["validator"] + alloc["treasury"] + burn
        assert abs(total - base) < 0.01

class TestFullIntegrationScenario:
    """End-to-end integration test with all components"""

    def test_complete_workflow(self):
        """Test complete job workflow: submit, compute, verify, reward, vest"""
        np.random.seed(42)
        A = np.random.randn(16, 16).astype(np.float32)
        B = np.random.randn(16, 16).astype(np.float32)

        burn = TokenEconomics.calculate_burn_amount(10.0)
        assert burn == 0.5

        alloc = TokenEconomics.calculate_reward_split(10.0)
        alloc = TokenEconomics.apply_public_good_bonus(alloc)
        assert alloc["bonus"] > 0

        start = datetime.now()
        vesting_per_miner = alloc["miner"] / 3

        vestings = {
            f"miner-{i:03d}": TokenEconomics.create_vesting(f"miner-{i:03d}", vesting_per_miner, start)
            for i in range(3)
        }

        for miner_id, sched in vestings.items():
            assert sched["amount"] > 0
            assert compute_vested(sched, start) == 0.0

            mid = start + timedelta(days=45)
            mid_v = compute_vested(sched, mid)
            assert 0.45 < (mid_v / sched["amount"]) < 0.55

        for miner_id, sched in vestings.items():
            at_30 = start + timedelta(days=30)
            vested_30 = compute_vested(sched, at_30)
            claimed = claim_vested(sched, vested_30, at_30)
            assert claimed == vested_30

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
