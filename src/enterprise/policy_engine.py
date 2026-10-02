"""Policy evaluation engine for Gillsystems AI Stack Updater Enterprise Edition.

Evaluates version updates against enterprise policy: pinned versions,
allowed ranges, approval requirements.
"""
from __future__ import annotations

from typing import Optional, Tuple

from packaging import version as pkg_version

from src.enterprise.policy import EnterprisePolicy, ComponentPolicy


class PolicyEngine:
    """Evaluates proposed updates against enterprise policy."""

    def __init__(self, policy: EnterprisePolicy):
        self.policy = policy

    def evaluate(
        self,
        component: str,
        current_version: Optional[str],
        proposed_version: Optional[str],
    ) -> Tuple[bool, str]:
        """
        Evaluate if a proposed version update is allowed by policy.

        Returns:
            (allowed: bool, reason: str)
        """
        comp_policy = self.policy.get_component_policy(component)
        if not comp_policy:
            return True, "No policy defined — update allowed"

        if proposed_version is None:
            return False, "No proposed version to evaluate"

        # Check pinned version (takes precedence over allow_range)
        if comp_policy.pinned_version and proposed_version != comp_policy.pinned_version:
            return False, (
                f"Pinned to {comp_policy.pinned_version}, proposed {proposed_version}. "
                "Pinned version takes precedence over allow_range."
            )

        # Check allow_range
        if comp_policy.allow_range:
            if not self._version_in_range(proposed_version, comp_policy.allow_range):
                return False, (
                    f"Version {proposed_version} outside allowed range {comp_policy.allow_range}"
                )

        # Check if current version is already at proposed (no-op)
        if current_version and current_version == proposed_version:
            return True, "Already at proposed version — no update needed"

        return True, "Allowed by policy"

    def requires_approval(self, component: str) -> bool:
        """Check if an update to this component requires human approval."""
        comp_policy = self.policy.get_component_policy(component)
        if not comp_policy:
            return False  # No policy = no approval required
        return comp_policy.requires_approval

    def get_mirror_url(self, component: str) -> Optional[str]:
        """Get internal mirror URL for air-gapped environments."""
        comp_policy = self.policy.get_component_policy(component)
        if comp_policy:
            return comp_policy.mirror_url
        return None

    def _version_in_range(self, ver: str, range_spec: str) -> bool:
        """
        Check if a version satisfies a range specification.

        Supports formats like:
        - ">=6.2.0,<7.0.0"
        - ">=b4500"
        - "==6.2.1"
        - "6.2.1" (exact match)
        """
        try:
            # Handle plain version as exact match
            if not any(range_spec.startswith(op) for op in (">=", "<=", ">", "<", "==", "!=")):
                range_spec = f"=={range_spec}"

            parts = [p.strip() for p in range_spec.split(",")]
            v = pkg_version.parse(ver)

            for part in parts:
                if part.startswith(">="):
                    if v < pkg_version.parse(part[2:]):
                        return False
                elif part.startswith("<="):
                    if v > pkg_version.parse(part[2:]):
                        return False
                elif part.startswith(">"):
                    if v <= pkg_version.parse(part[1:]):
                        return False
                elif part.startswith("<"):
                    if v >= pkg_version.parse(part[1:]):
                        return False
                elif part.startswith("=="):
                    if v != pkg_version.parse(part[2:]):
                        return False
                elif part.startswith("!="):
                    if v == pkg_version.parse(part[2:]):
                        return False
                else:
                    # Unknown operator, fail open with warning
                    return True

            return True
        except Exception:
            # Fail open on parse error — log and allow
            return True


def load_enterprise_policy(policy_path: str) -> EnterprisePolicy:
    """Load enterprise policy from YAML file."""
    import yaml
    from pathlib import Path

    path = Path(policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Enterprise policy file not found: {policy_path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return EnterprisePolicy.model_validate(raw)