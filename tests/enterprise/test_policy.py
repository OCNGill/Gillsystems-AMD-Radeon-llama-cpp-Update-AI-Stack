"""Tests for enterprise policy module."""
import pytest
from src.enterprise.policy import (
    ComponentPolicy,
    ApprovalGate,
    FleetPolicy,
    EnterprisePolicy,
)


def test_component_policy_defaults():
    policy = ComponentPolicy()
    assert policy.pinned_version is None
    assert policy.allow_range is None
    assert policy.requires_approval is True
    assert policy.auto_approve_security is False
    assert policy.mirror_url is None


def test_component_policy_with_values():
    policy = ComponentPolicy(
        pinned_version="6.2.1",
        allow_range=">=6.2.0,<7.0.0",
        requires_approval=True,
        auto_approve_security=False,
        mirror_url="https://internal-mirror.example.com/rocm"
    )
    assert policy.pinned_version == "6.2.1"
    assert policy.allow_range == ">=6.2.0,<7.0.0"
    assert policy.requires_approval is True
    assert policy.auto_approve_security is False
    assert policy.mirror_url == "https://internal-mirror.example.com/rocm"


def test_approval_gate_defaults():
    gate = ApprovalGate()
    assert gate.default_approvers == []
    assert gate.auto_approve_security is False
    assert gate.timeout_hours == 72
    assert gate.require_mfa is True


def test_fleet_policy_defaults():
    fleet = FleetPolicy()
    assert fleet.max_concurrent_nodes == 4
    assert fleet.failure_threshold == 0.25
    assert fleet.rolling_update is True
    assert fleet.batch_size == 2


def test_enterprise_policy_empty():
    policy = EnterprisePolicy()
    assert policy.managed_components == {}
    assert isinstance(policy.approval_gates, ApprovalGate)
    assert isinstance(policy.fleet, FleetPolicy)
    assert policy.get_component_policy("rocm") is None
    assert policy.is_managed("rocm") is False


def test_enterprise_policy_with_components():
    policy = EnterprisePolicy(
        managed_components={
            "rocm": ComponentPolicy(pinned_version="6.2.1", requires_approval=True),
            "llama.cpp": ComponentPolicy(allow_range=">=b4500", requires_approval=False),
        }
    )
    assert policy.is_managed("rocm") is True
    assert policy.is_managed("llama.cpp") is True
    assert policy.is_managed("unknown") is False

    rocm_policy = policy.get_component_policy("rocm")
    assert rocm_policy is not None
    assert rocm_policy.pinned_version == "6.2.1"

    llama_policy = policy.get_component_policy("llama.cpp")
    assert llama_policy is not None
    assert llama_policy.allow_range == ">=b4500"
    assert llama_policy.requires_approval is False


def test_enterprise_policy_yaml_parsing():
    """Test that the default YAML template parses correctly."""
    import yaml
    from src.enterprise.policy import DEFAULT_ENTERPRISE_POLICY_YAML

    raw = yaml.safe_load(DEFAULT_ENTERPRISE_POLICY_YAML)
    policy = EnterprisePolicy.model_validate(raw)

    assert policy.is_managed("rocm")
    assert policy.is_managed("llama.cpp")
    assert policy.get_component_policy("rocm").pinned_version == "6.2.1"
    assert policy.get_component_policy("llama.cpp").allow_range == ">=b4500"
    assert len(policy.approval_gates.default_approvers) == 2
    assert policy.fleet.max_concurrent_nodes == 4