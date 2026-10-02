"""Enterprise policy configuration models for Gillsystems AI Stack Updater Enterprise Edition.

Defines declarative policy for managed components with version pinning,
allowed ranges, approval gates, and air-gapped mirror support.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ComponentPolicy(BaseModel):
    """Policy for a single managed component (e.g., ROCm, llama.cpp)."""

    pinned_version: Optional[str] = Field(
        default=None,
        description="Exact version to pin (overrides allow_range). Example: '6.2.1' or 'b4567'"
    )
    allow_range: Optional[str] = Field(
        default=None,
        description="Semver/version range allowed (e.g., '>=6.2.0,<7.0.0' or '>=b4500'). "
                    "If both pinned_version and allow_range are set, pinned_version takes precedence."
    )
    requires_approval: bool = Field(
        default=True,
        description="Require human approval before applying update to this component."
    )
    auto_approve_security: bool = Field(
        default=False,
        description="Auto-approve security-only updates (CVE patches) without human review."
    )
    mirror_url: Optional[str] = Field(
        default=None,
        description="Internal mirror URL for air-gapped environments. "
                    "Overrides default upstream repos when set."
    )


class ApprovalGate(BaseModel):
    """Approval gate configuration for the enterprise updater."""

    default_approvers: List[str] = Field(
        default_factory=list,
        description="List of email addresses or user IDs authorized to approve updates."
    )
    auto_approve_security: bool = Field(
        default=False,
        description="Globally auto-approve security-only updates across all components."
    )
    timeout_hours: int = Field(
        default=72,
        ge=1,
        le=720,
        description="Hours before an approval request expires (1-720 hours / 1-30 days)."
    )
    require_mfa: bool = Field(
        default=True,
        description="Require multi-factor authentication for approval actions."
    )


class FleetPolicy(BaseModel):
    """Fleet-wide policy settings (for T-104 fleet orchestration)."""

    max_concurrent_nodes: int = Field(
        default=4,
        ge=1,
        le=64,
        description="Maximum number of nodes to update concurrently."
    )
    failure_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Fraction of nodes that can fail before fleet update is aborted (0.0-1.0)."
    )
    rolling_update: bool = Field(
        default=True,
        description="Update nodes in rolling fashion (one batch at a time) vs all at once."
    )
    batch_size: int = Field(
        default=2,
        ge=1,
        le=32,
        description="Number of nodes per rolling batch."
    )


class EnterprisePolicy(BaseModel):
    """Root enterprise policy configuration."""

    managed_components: Dict[str, ComponentPolicy] = Field(
        default_factory=dict,
        description="Policy per managed component (key = component name: 'rocm', 'llama.cpp', etc.)"
    )
    approval_gates: ApprovalGate = Field(
        default_factory=ApprovalGate,
        description="Global approval gate settings."
    )
    fleet: FleetPolicy = Field(
        default_factory=FleetPolicy,
        description="Fleet orchestration policy (T-104)."
    )

    def get_component_policy(self, component: str) -> Optional[ComponentPolicy]:
        """Get policy for a specific component."""
        return self.managed_components.get(component)

    def is_managed(self, component: str) -> bool:
        """Check if a component has policy defined."""
        return component in self.managed_components


# Default enterprise policy template for reference
DEFAULT_ENTERPRISE_POLICY_YAML = """
# Enterprise Policy Configuration
# Place at config/enterprise_policy.yaml and reference via --enterprise-policy flag

managed_components:
  rocm:
    pinned_version: "6.2.1"
    allow_range: ">=6.2.0,<7.0.0"
    requires_approval: true
    auto_approve_security: false
    mirror_url: "https://internal-mirror.company.com/rocm"
  
  llama.cpp:
    pinned_version: null
    allow_range: ">=b4500"
    requires_approval: true
    auto_approve_security: true
    mirror_url: "https://internal-mirror.company.com/llama.cpp"

approval_gates:
  default_approvers:
    - "platform-team@company.com"
    - "security-team@company.com"
  auto_approve_security: false
  timeout_hours: 72
  require_mfa: true

fleet:
  max_concurrent_nodes: 4
  failure_threshold: 0.25
  rolling_update: true
  batch_size: 2
"""