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
- Immutable change logs (append-only, hash-chained)
- Role-based approval gates
- FIPS 140-2 compatible crypto for secrets

## Public/Private Split
- **Public** (`Gillsystems-AMD-Radeon-llama-cpp-Update-AI-Stack`): Open source, serves individual developers and small teams. MIT license.
- **Private** (this repo): Enterprise features, proprietary license. No enterprise code in public repo.