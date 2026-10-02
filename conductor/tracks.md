# Tracks Registry — Enterprise Edition

## Active Tracks
| Track | Folder | Status | 7D Phase |
|-------|--------|--------|----------|
| T-100: Enterprise Foundation | `conductor/tracks/T-100-enterprise-foundation/` | **In Progress** | Initiate |
| T-101: Policy-Driven Updates | `conductor/tracks/T-101-policy-driven-updates/` | Planned | Plan |

## Planned Tracks (Enterprise Delta)
| Track | Folder | Priority | Description |
|-------|--------|----------|-------------|
| T-100: Enterprise Foundation | `conductor/tracks/T-100-enterprise-foundation/` | 1 | Private repo setup, conductor, base enterprise module structure |
| T-101: Policy-Driven Updates | `conductor/tracks/T-101-policy-driven-updates/` | 1 | Declarative config: pinned versions, allowed ranges, approval gates |
| T-102: Audit Log | `conductor/tracks/T-102-audit-log/` | 1 | Immutable hash-chained audit trail for every change |
| T-103: Rollback | `conductor/tracks/T-103-rollback/` | 1 | Pre-update state capture, reversible updates |
| T-104: Fleet Orchestration | `conductor/tracks/T-104-fleet-orchestration/` | 2 | Multi-node targeting, concurrency, partial failure handling |
| T-105: Air-Gapped/Offline | `conductor/tracks/T-105-airgapped/` | 2 | Internal mirror support, no internet required |
| T-106: Secrets & Auth | `conductor/tracks/T-106-secrets-auth/` | 2 | Service accounts, vault integration, no plaintext creds |
| T-107: Reporting | `conductor/tracks/T-107-reporting/` | 3 | Compliance reports, current vs desired across fleet |
| T-108: Unattended Service | `conductor/tracks/T-108-unattended/` | 3 | Windows service / systemd unit, not human at terminal |

## Public Baseline (Reference Only)
| Track | Version | Date | Notes |
|-------|---------|------|-------|
| T-001: Agent Architecture & Core | v2.6.0 | 2026-09-21 | Public repo: packaged, multi-gen GPU detection, privacy scrub, 113/113 tests |
| T-001: Agent Architecture & Core | v2.5.0 | 2026-09-17 | Headless sudo validation, ROCm timeout, --skip-rocm fix |
| T-001: Agent Architecture & Core | v2.4.0 | 2026-05-29 | 4 launcher bugs fixed, Gemma 4 tuning reference |
| T-001: Agent Architecture & Core | v2.3.0 | 2026-05-28 | KV-cache q8_0 optimization |
| T-001: Agent Architecture & Core | v2.1.0 | 2026-05-27 | Round 3/4 launcher stabilization |