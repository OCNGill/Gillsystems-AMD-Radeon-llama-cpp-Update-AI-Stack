# E2D-T3 Enterprise Edition: PRIVATE AI Stack Updater Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fork the proven public CLI AI Stack Updater into a PRIVATE "Enterprise" edition with policy-driven updates, audit logging, and rollback — the highest-value enterprise delta per Commander directive.

**Architecture:** Private repo mirrors public structure but adds enterprise modules (policy, audit, rollback, fleet, secrets) as additive layers. Public repo remains untouched and open source. Enterprise edition loads public core + enterprise extensions.

**Tech Stack:** Python 3.13, Pydantic v2, Rich, SQLite (existing), PyYAML, httpx. NO GitHub Actions (local builds only). 7D Conductor mandatory.

---

## Phase 1: Private Repo Setup & Foundation

### Task 1: Create Private Enterprise Repository

**Objective:** Create private GitHub repo `Gillsystems-AI-Stack-Updater-Enterprise` under OCNGill org with verified private visibility.

**Files:**
- Create: (remote repo only — no local files yet)

**Step 1: Create private repo via GitHub API**

```bash
# Using gh CLI (preferred)
gh repo create OCNGill/Gillsystems-AI-Stack-Updater-Enterprise --private --description "Enterprise edition: policy-driven updates, fleet orchestration, audit log, rollback. Private fork of public AI Stack Updater." --clone
```

**Step 2: Verify privacy**

```bash
gh repo view OCNGill/Gillsystems-AI-Stack-Updater-Enterprise --json visibility,name
# Expected: {"visibility": "private", "name": "Gillsystems-AI-Stack-Updater-Enterprise"}
```

**Step 3: Commit initial structure**

```bash
cd Gillsystems-AI-Stack-Updater-Enterprise
# Copy public repo structure as baseline
git commit --allow-empty -m "chore: initialize enterprise edition from public v2.6.0 baseline"
git push origin main
```

---

### Task 2: Create 7D Conductor Files for Enterprise Edition

**Objective:** Establish mandatory 7D Conductor documentation in the private repo.

**Files:**
- Create: `conductor/product.md`
- Create: `conductor/setup_state.json`
- Create: `conductor/tracks.md`
- Create: `conductor/tracks/T-100-enterprise-foundation/`
- Create: `conductor/tracks/T-101-policy-driven-updates/`
- Create: `conductor/tracks/T-102-audit-log/`
- Create: `conductor/tracks/T-103-rollback/`
- Create: `conductor/tracks/T-104-fleet-orchestration/`
- Create: `conductor/tracks/T-105-airgapped/`
- Create: `conductor/tracks/T-106-secrets-auth/`
- Create: `conductor/tracks/T-107-reporting/`
- Create: `conductor/tracks/T-108-unattended/`
- Create: `CHANGELOG.md` (at repo root, symlinked from conductor/)

**Step 1: Create product.md**

```markdown
# Product Definition — Gillsystems AI Stack Updater Enterprise Edition

## Mission
Provide an enterprise-grade, policy-driven AI stack update platform with full governance, audit trails, rollback capability, and fleet orchestration for air-gapped and multi-node environments.

## Core Value (Enterprise Delta)
**Control, Governance, Scale** — not new update logic. OS's don't change, software doesn't change. Enterprise value is DECIDING what changes, not whatever the CLI found.

## Enterprise Capabilities (Priority Order)
1. **Policy-Driven Updates** — Declarative config: managed runtimes/models/tools, pinned versions, allowed ranges, approval gates.
2. **Audit Log** — Every change gets a diff, an approval step, an immutable record of who/when.
3. **Rollback** — Every update reversible, previous state captured first.
4. **Fleet/Multi-Node Orchestration** — Fleet targeting, concurrency limits, partial-failure handling.
5. **Air-Gapped / Offline** — Works from internal mirror with no internet.
6. **Secrets + Auth** — No plaintext credentials, service-account auth, least privilege.
7. **Reporting** — Scheduled compliance reports, current vs desired across fleet.
8. **Unattended** — Windows service/scheduled task, not a human at a terminal.

## Target Environments
| Environment | OS | Network | Use Case |
|-------------|-----|---------|----------|
| Enterprise DC | Windows Server 2022 / RHEL 9 | Air-gapped | GPU inference cluster |
| Edge Nodes | Ubuntu 22.04 / Windows 11 | Intermittent | Inference at edge |
| Dev Workstations | Windows 11 / Fedora | Connected | Developer AI stack mgmt |

## Compliance Requirements
- SOC 2 Type II audit trail
- Immutable change logs (append-only)
- Role-based approval gates
- FIPS 140-2 compatible crypto for secrets
```

**Step 2: Create setup_state.json**

```json
{
  "version": "0.1.0-enterprise",
  "initialized": "2026-10-02T00:00:00Z",
  "public_baseline": "v2.6.0",
  "tracks": {
    "T-100-enterprise-foundation": "planned",
    "T-101-policy-driven-updates": "planned",
    "T-102-audit-log": "planned",
    "T-103-rollback": "planned",
    "T-104-fleet-orchestration": "planned",
    "T-105-airgapped": "planned",
    "T-106-secrets-auth": "planned",
    "T-107-reporting": "planned",
    "T-108-unattended": "planned"
  },
  "public_repo": "OCNGill/Gillsystems-AMD-Radeon-llama-cpp-Update-AI-Stack",
  "private_repo": "OCNGill/Gillsystems-AI-Stack-Updater-Enterprise"
}
```

**Step 3: Create tracks.md with all enterprise tracks**

**Step 4: Create CHANGELOG.md at root with v0.1.0-enterprise entry**

```markdown
# CHANGELOG

## [0.1.0-enterprise] - 2026-10-02
### Added
- Enterprise edition initialized from public v2.6.0 baseline
- Private repository created with verified private visibility
- 7D Conductor structure established for enterprise tracks

> **Verse:** Proverbs 16:3 — "Commit to the Lord whatever you do, and he will establish your plans." — Foundation laid on solid ground before building.
```

**Step 5: Verify conductor symlink**

```bash
ln -sf ../CHANGELOG.md conductor/CHANGELOG.md
ls -la conductor/CHANGELOG.md
```

---

## Phase 2: Policy-Driven Updates (T-101) — Highest Value

### Task 3: Create Policy Configuration Schema

**Objective:** Define declarative policy schema for managed components with version pinning, ranges, and approval gates.

**Files:**
- Create: `src/enterprise/policy.py`
- Create: `src/enterprise/__init__.py`
- Modify: `src/config.py` (add enterprise policy section)

**Step 1: Write failing test for policy schema**

```python
# tests/enterprise/test_policy.py
def test_policy_schema_loads_valid_config():
    from src.enterprise.policy import EnterprisePolicy
    policy = EnterprisePolicy.model_validate({
        "managed_components": {
            "rocm": {"pinned_version": "6.2.1", "allow_range": ">=6.2.0,<7.0.0", "requires_approval": True},
            "llama.cpp": {"pinned_version": "b4567", "allow_range": ">=b4500", "requires_approval": False}
        },
        "approval_gates": {"default_approvers": ["admin@company.com"], "auto_approve_security": False}
    })
    assert policy.managed_components["rocm"].pinned_version == "6.2.1"
    assert policy.managed_components["rocm"].requires_approval is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/enterprise/test_policy.py::test_policy_schema_loads_valid_config -v
# Expected: FAIL — module not found
```

**Step 3: Implement policy.py with Pydantic models**

```python
# src/enterprise/policy.py
from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ComponentPolicy(BaseModel):
    """Policy for a single managed component."""
    pinned_version: Optional[str] = Field(default=None, description="Exact version to pin (overrides allow_range)")
    allow_range: Optional[str] = Field(default=None, description="Semver/version range allowed (e.g., '>=6.2.0,<7.0.0')")
    requires_approval: bool = Field(default=True, description="Require human approval before applying update")
    auto_approve_security: bool = Field(default=False, description="Auto-approve security-only updates")
    mirror_url: Optional[str] = Field(default=None, description="Internal mirror URL for air-gapped environments")

class ApprovalGate(BaseModel):
    """Approval gate configuration."""
    default_approvers: List[str] = Field(default_factory=list)
    auto_approve_security: bool = False
    timeout_hours: int = Field(default=72, description="Hours before approval request expires")

class EnterprisePolicy(BaseModel):
    """Root enterprise policy configuration."""
    managed_components: Dict[str, ComponentPolicy] = Field(default_factory=dict)
    approval_gates: ApprovalGate = Field(default_factory=ApprovalGate)
    fleet: Dict = Field(default_factory=dict)  # For T-104
    
    def get_component_policy(self, component: str) -> Optional[ComponentPolicy]:
        return self.managed_components.get(component)
    
    def is_update_allowed(self, component: str, current: str, proposed: str) -> tuple[bool, str]:
        """Check if proposed version is allowed by policy."""
        policy = self.get_component_policy(component)
        if not policy:
            return True, "No policy defined — update allowed"
        if policy.pinned_version and proposed != policy.pinned_version:
            return False, f"Pinned to {policy.pinned_version}, proposed {proposed}"
        # TODO: implement range checking with packaging.version
        return True, "Allowed"
```

**Step 4: Run test to verify pass**

```bash
pytest tests/enterprise/test_policy.py::test_policy_schema_loads_valid_config -v
# Expected: PASS
```

**Step 5: Add enterprise config to config.py**

```python
# In src/config.py, add to GillsystemsAIStackUpdaterConfig:
# enterprise_policy: Optional[EnterprisePolicy] = Field(default=None)
# And loader integration
```

**Step 6: Commit**

```bash
git add src/enterprise/policy.py src/enterprise/__init__.py tests/enterprise/test_policy.py src/config.py
git commit -m "feat(enterprise): add policy-driven updates schema (T-101)"
```

---

### Task 4: Implement Policy Evaluation Engine

**Objective:** Integrate policy evaluation into the version check flow — enforce pins, ranges, and approval requirements.

**Files:**
- Create: `src/enterprise/policy_engine.py`
- Modify: `src/version_intel.py` (add policy evaluation)
- Modify: `src/main.py` (integrate policy check before confirmation)

**Step 1: Write failing test**

```python
# tests/enterprise/test_policy_engine.py
def test_policy_engine_blocks_pinned_version():
    from src.enterprise.policy_engine import PolicyEngine
    from src.enterprise.policy import EnterprisePolicy, ComponentPolicy
    policy = EnterprisePolicy(managed_components={
        "rocm": ComponentPolicy(pinned_version="6.2.1", requires_approval=True)
    })
    engine = PolicyEngine(policy)
    allowed, reason = engine.evaluate("rocm", "6.2.1", "6.3.0")
    assert allowed is False
    assert "Pinned to 6.2.1" in reason
```

**Step 2: Implement policy_engine.py**

```python
# src/enterprise/policy_engine.py
from __future__ import annotations
from typing import Optional, Tuple
from packaging import version as pkg_version

from src.enterprise.policy import EnterprisePolicy, ComponentPolicy

class PolicyEngine:
    def __init__(self, policy: EnterprisePolicy):
        self.policy = policy
    
    def evaluate(self, component: str, current: str, proposed: str) -> Tuple[bool, str]:
        comp_policy = self.policy.get_component_policy(component)
        if not comp_policy:
            return True, "No policy defined — update allowed"
        
        # Check pinned version
        if comp_policy.pinned_version and proposed != comp_policy.pinned_version:
            return False, f"Pinned to {comp_policy.pinned_version}, proposed {proposed}"
        
        # Check allow_range
        if comp_policy.allow_range:
            if not self._version_in_range(proposed, comp_policy.allow_range):
                return False, f"Version {proposed} outside allowed range {comp_policy.allow_range}"
        
        return True, "Allowed"
    
    def requires_approval(self, component: str) -> bool:
        comp_policy = self.policy.get_component_policy(component)
        return comp_policy.requires_approval if comp_policy else False
    
    def _version_in_range(self, ver: str, range_spec: str) -> bool:
        # Simplified: parse range like ">=6.2.0,<7.0.0"
        try:
            parts = [p.strip() for p in range_spec.split(",")]
            v = pkg_version.parse(ver)
            for part in parts:
                if part.startswith(">="):
                    if v < pkg_version.parse(part[2:]): return False
                elif part.startswith("<="):
                    if v > pkg_version.parse(part[2:]): return False
                elif part.startswith(">"):
                    if v <= pkg_version.parse(part[1:]): return False
                elif part.startswith("<"):
                    if v >= pkg_version.parse(part[1:]): return False
                elif part.startswith("=="):
                    if v != pkg_version.parse(part[2:]): return False
            return True
        except Exception:
            return True  # Fail open on parse error
```

**Step 3: Integrate into version_intel.py UpdateManifest**

```python
# In src/version_intel.py UpdateManifest.add_policy_evaluation(policy_engine)
# Add policy_allowed and policy_reason fields to each component result
```

**Step 4: Modify main.py to show policy status in version table**

```python
# In _step_check_versions: after manifest = self.intel.check_all()
# if self.cfg.enterprise_policy:
#     engine = PolicyEngine(self.cfg.enterprise_policy)
#     for component in [manifest.rocm, manifest.llama_cpp]:
#         allowed, reason = engine.evaluate(component.name, component.installed, component.latest)
#         component.policy_allowed = allowed
#         component.policy_reason = reason
```

**Step 5: Run tests, commit**

---

### Task 5: Add Approval Gate Workflow

**Objective:** Implement approval request/response flow with timeout and audit trail.

**Files:**
- Create: `src/enterprise/approval.py`
- Modify: `src/main.py` (insert approval step before updates)

**Implementation:** Approval requests written to audit log, await response via file/DB/webhook, timeout after configurable hours.

---

## Phase 3: Audit Log (T-102) — Immutable Change Records

### Task 6: Create Audit Log Schema & Storage

**Objective:** Append-only audit log with cryptographic integrity (hash chaining) for every change.

**Files:**
- Create: `src/enterprise/audit.py`
- Create: `tests/enterprise/test_audit.py`

**Schema:**
```python
class AuditEntry(BaseModel):
    id: str  # UUID
    timestamp: str  # ISO 8601 UTC
    actor: str  # user/service account
    action: str  # "update_rocm", "update_llama", "policy_change", "approval_grant", "rollback"
    component: str
    old_version: Optional[str]
    new_version: Optional[str]
    diff: Optional[str]  # Unified diff of changes
    policy_decision: Optional[dict]  # allowed/denied, reason
    approval: Optional[dict]  # request_id, approver, timestamp
    hash_chain: str  # SHA256(prev_hash + current_entry_json)
```

**Storage:** SQLite table `audit_log` with hash_chain index for tamper detection.

---

### Task 7: Integrate Audit Logging into Orchestrator

**Objective:** Every state transition in main.py writes an audit entry.

**Files:**
- Modify: `src/main.py` (import audit, call at each step)
- Modify: `src/state_manager.py` (extend with audit integration)

---

## Phase 4: Rollback (T-103) — Reversible Updates

### Task 8: Implement Pre-Update State Capture

**Objective:** Before any mutating operation, capture complete state snapshot for rollback.

**Files:**
- Create: `src/enterprise/rollback.py`
- Modify: `src/main.py` (capture before ROCm/llama updates)

**Capture:** 
- Installed binary hashes (SHA256)
- Config file snapshots
- Version metadata
- GPU detection results

### Task 9: Implement Rollback Command

**Objective:** `gillsystems-ai-stack-updater-enterprise rollback --component rocm --to-version 6.1.0`

**Files:**
- Create: `src/enterprise/rollback_cli.py`
- Modify: `src/cli.py` (add rollback subcommand)
- Modify: `src/main.py` (add rollback entry point)

---

## Phase 5: Fleet Orchestration (T-104)

### Task 10: Fleet Targeting & Inventory

**Files:**
- Create: `src/enterprise/fleet.py` (Node, Fleet, Target models)
- Create: `src/enterprise/inventory.py` (discovery via SSH/WinRM)

### Task 11: Parallel Execution with Concurrency Limits

**Files:**
- Create: `src/enterprise/fleet_orchestrator.py`
- Modify: `src/main.py` (add --fleet, --target-nodes, --concurrency flags)

---

## Phase 6: Air-Gapped / Offline (T-105)

### Task 12: Mirror Configuration & Validation

**Files:**
- Create: `src/enterprise/mirror.py`
- Modify: `src/config.py` (add mirror URLs to RepoConfig)
- Modify: `src/version_intel.py` (use mirror for version checks)

---

## Phase 7: Secrets & Auth (T-106)

### Task 13: Secrets Manager Integration

**Files:**
- Create: `src/enterprise/secrets.py` (Azure Key Vault, HashiCorp Vault, AWS Secrets Manager, local encrypted)
- Modify: `src/config.py` (load secrets at runtime, never in config files)

---

## Phase 8: Reporting (T-107)

### Task 14: Compliance Report Generator

**Files:**
- Create: `src/enterprise/reporting.py`
- Create: `src/enterprise/templates/report.html.j2`
- Modify: `src/cli.py` (add --report flag)

---

## Phase 9: Unattended Service (T-108)

### Task 15: Windows Service & Linux Systemd Unit

**Files:**
- Create: `scripts/install_service_windows.ps1`
- Create: `scripts/install_service_linux.sh`
- Create: `src/enterprise/service_runner.py` (daemon mode with config watch)

---

## Deliverables Checklist

- [ ] Private repo created and verified private
- [ ] 7D Conductor files created
- [ ] Policy-driven updates (T-101) implemented and tested
- [ ] Audit log (T-102) implemented and tested
- [ ] Rollback (T-103) implemented and tested
- [ ] README explaining public/private split
- [ ] All commits pushed to PRIVATE repo only
- [ ] `gh repo view --json visibility,name` shows private

---

## Acceptance Criteria

1. **Private repo verified:** `gh repo view OCNGill/Gillsystems-AI-Stack-Updater-Enterprise --json visibility` returns `"private"`
2. **Policy enforcement:** `--dry-run` shows policy decision (allowed/blocked) for each component
3. **Audit log:** Every update attempt creates immutable hash-chained entry
4. **Rollback:** `rollback` command restores previous binary hashes and config
5. **No public repo modifications:** `git diff` in public repo shows no changes
6. **Python 3.13 compatible:** No syntax errors, all tests pass
7. **7D Conductor:** All files present, CHANGELOG symlinked