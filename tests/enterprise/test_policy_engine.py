"""Tests for enterprise policy engine."""
import pytest
from src.enterprise.policy import EnterprisePolicy, ComponentPolicy
from src.enterprise.policy_engine import PolicyEngine


def test_policy_engine_allows_when_no_policy():
    policy = EnterprisePolicy()
    engine = PolicyEngine(policy)

    allowed, reason = engine.evaluate("rocm", "6.1.0", "6.2.0")
    assert allowed is True
    assert "No policy defined" in reason


def test_policy_engine_blocks_pinned_version():
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(pinned_version="6.2.1", requires_approval=True)
    })
    engine = PolicyEngine(policy)

    # Different version should be blocked
    allowed, reason = engine.evaluate("rocm", "6.2.1", "6.3.0")
    assert allowed is False
    assert "Pinned to 6.2.1" in reason

    # Same version should be allowed (no-op)
    allowed, reason = engine.evaluate("rocm", "6.2.1", "6.2.1")
    assert allowed is True
    assert "Already at proposed version" in reason


def test_policy_engine_allows_within_range():
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(allow_range=">=6.2.0,<7.0.0", requires_approval=True)
    })
    engine = PolicyEngine(policy)

    # Within range
    allowed, reason = engine.evaluate("rocm", "6.1.0", "6.2.5")
    assert allowed is True

    # Below range
    allowed, reason = engine.evaluate("rocm", "6.1.0", "6.1.0")
    assert allowed is False
    assert "outside allowed range" in reason

    # Above range
    allowed, reason = engine.evaluate("rocm", "6.1.0", "7.0.0")
    assert allowed is False
    assert "outside allowed range" in reason


def test_policy_engine_pinned_takes_precedence():
    """Pinned version should take precedence over allow_range."""
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(
            pinned_version="6.2.1",
            allow_range=">=6.2.0,<7.0.0",
            requires_approval=True
        )
    })
    engine = PolicyEngine(policy)

    # Even though 6.3.0 is in allow_range, pinned_version blocks it
    allowed, reason = engine.evaluate("rocm", "6.2.1", "6.3.0")
    assert allowed is False
    assert "Pinned to 6.2.1" in reason


def test_policy_engine_exact_match_range():
    """Test exact version match with == operator."""
    policy = EnterprisePolicy(managed_components={
        "llama.cpp": ComponentPolicy(allow_range="==1.2.3", requires_approval=True)
    })
    engine = PolicyEngine(policy)

    allowed, reason = engine.evaluate("llama.cpp", "1.2.2", "1.2.3")
    assert allowed is True

    allowed, reason = engine.evaluate("llama.cpp", "1.2.2", "1.2.4")
    assert allowed is False


def test_policy_engine_requires_approval():
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(requires_approval=True),
        "llama.cpp": ComponentPolicy(requires_approval=False),
    })
    engine = PolicyEngine(policy)

    assert engine.requires_approval("rocm") is True
    assert engine.requires_approval("llama.cpp") is False
    assert engine.requires_approval("unknown") is False


def test_policy_engine_get_mirror_url():
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(mirror_url="https://mirror.internal/rocm"),
        "llama.cpp": ComponentPolicy(mirror_url=None),
    })
    engine = PolicyEngine(policy)

    assert engine.get_mirror_url("rocm") == "https://mirror.internal/rocm"
    assert engine.get_mirror_url("llama.cpp") is None
    assert engine.get_mirror_url("unknown") is None


def test_policy_engine_invalid_range_fails_open():
    """Invalid range spec should fail open (allow) with warning."""
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(allow_range="invalid-range-spec", requires_approval=True)
    })
    engine = PolicyEngine(policy)

    # Should fail open
    allowed, reason = engine.evaluate("rocm", "6.1.0", "6.3.0")
    assert allowed is True