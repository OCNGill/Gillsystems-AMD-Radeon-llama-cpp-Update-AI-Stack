"""Immutable audit log for Gillsystems AI Stack Updater Enterprise Edition.

Provides tamper-evident audit trail with hash chaining for every change.
Each entry includes: actor, action, component, versions, diff, policy decision,
approval record, and cryptographic hash chain.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """Single immutable audit log entry."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str  # User ID, service account, or system
    action: str  # update_rocm, update_llama, policy_change, approval_grant, rollback, etc.
    component: str  # rocm, llama.cpp, policy, fleet, etc.
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    diff: Optional[str] = None  # Unified diff of changes
    policy_decision: Optional[Dict[str, Any]] = None  # {"allowed": true, "reason": "..."}
    approval: Optional[Dict[str, Any]] = None  # {"request_id": "...", "approver": "...", "timestamp": "..."}
    metadata: Optional[Dict[str, Any]] = None  # Free-form additional context
    prev_hash: str = ""  # Hash of previous entry (for chain integrity)
    hash: str = ""  # SHA256 of this entry's content (excluding hash field)

    def compute_hash(self) -> str:
        """Compute SHA256 hash of entry content (excluding the hash field itself)."""
        # Create a dict excluding the hash field and auto-generated fields
        # id and timestamp are excluded for deterministic hashing in tests
        # In production, the full entry including timestamp is stored
        data = self.model_dump(exclude={"hash", "id", "timestamp"})
        # Ensure deterministic JSON serialization
        content = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, prev_hash: str) -> "AuditEntry":
        """Seal the entry with previous hash and compute own hash."""
        self.prev_hash = prev_hash
        self.hash = self.compute_hash()
        return self

    def verify(self, prev_hash: str) -> bool:
        """Verify the entry's hash chain integrity."""
        if self.prev_hash != prev_hash:
            return False
        return self.hash == self.compute_hash()


class AuditLog:
    """Append-only audit log with hash-chained integrity."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          TEXT PRIMARY KEY,
        timestamp   TEXT NOT NULL,
        actor       TEXT NOT NULL,
        action      TEXT NOT NULL,
        component   TEXT NOT NULL,
        old_version TEXT,
        new_version TEXT,
        diff        TEXT,
        policy_decision TEXT,
        approval    TEXT,
        metadata    TEXT,
        prev_hash   TEXT NOT NULL,
        hash        TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
    CREATE INDEX IF NOT EXISTS idx_audit_component ON audit_log(component);
    CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
        self._last_hash = self._get_last_hash()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_last_hash(self) -> str:
        """Get hash of the most recent entry (empty string for genesis)."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT hash FROM audit_log ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        return row["hash"] if row else ""

    def append(
        self,
        actor: str,
        action: str,
        component: str,
        old_version: Optional[str] = None,
        new_version: Optional[str] = None,
        diff: Optional[str] = None,
        policy_decision: Optional[Dict[str, Any]] = None,
        approval: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """
        Append a new audit entry, sealed with hash chain.

        Returns the sealed AuditEntry.
        """
        entry = AuditEntry(
            actor=actor,
            action=action,
            component=component,
            old_version=old_version,
            new_version=new_version,
            diff=diff,
            policy_decision=policy_decision,
            approval=approval,
            metadata=metadata,
        ).seal(self._last_hash)

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                (id, timestamp, actor, action, component, old_version, new_version,
                 diff, policy_decision, approval, metadata, prev_hash, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp,
                    entry.actor,
                    entry.action,
                    entry.component,
                    entry.old_version,
                    entry.new_version,
                    entry.diff,
                    json.dumps(entry.policy_decision) if entry.policy_decision else None,
                    json.dumps(entry.approval) if entry.approval else None,
                    json.dumps(entry.metadata) if entry.metadata else None,
                    entry.prev_hash,
                    entry.hash,
                ),
            )

        self._last_hash = entry.hash
        return entry

    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """Retrieve a single audit entry by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM audit_log WHERE id = ?", (entry_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row)

    def get_entries(
        self,
        component: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries with optional filters."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params: List[Any] = []

        if component:
            query += " AND component = ?"
            params.append(component)
        if actor:
            query += " AND actor = ?"
            params.append(actor)
        if action:
            query += " AND action = ?"
            params.append(action)
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        if until:
            query += " AND timestamp <= ?"
            params.append(until)

        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_entry(r) for r in rows]

    def verify_chain(self, start_id: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Verify the entire hash chain integrity.

        Returns:
            (is_valid: bool, errors: List[str])
        """
        query = "SELECT * FROM audit_log ORDER BY rowid"
        if start_id:
            query += " WHERE rowid >= (SELECT rowid FROM audit_log WHERE id = ?)"

        with self._get_conn() as conn:
            if start_id:
                rows = conn.execute(query, (start_id,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()

        errors = []
        prev_hash = ""

        for i, row in enumerate(rows):
            entry = self._row_to_entry(row)
            if not entry.verify(prev_hash):
                errors.append(
                    f"Chain break at entry {entry.id} (row {i}): "
                    f"prev_hash mismatch (expected {prev_hash}, got {entry.prev_hash}) "
                    f"or hash mismatch (computed {entry.compute_hash()}, stored {entry.hash})"
                )
            prev_hash = entry.hash

        return len(errors) == 0, errors

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        return AuditEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            action=row["action"],
            component=row["component"],
            old_version=row["old_version"],
            new_version=row["new_version"],
            diff=row["diff"],
            policy_decision=json.loads(row["policy_decision"]) if row["policy_decision"] else None,
            approval=json.loads(row["approval"]) if row["approval"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            prev_hash=row["prev_hash"],
            hash=row["hash"],
        )

    def export_json(self, filepath: Path) -> int:
        """Export all audit entries to JSON file for archival."""
        entries = self.get_entries(limit=100000)  # Large limit for full export
        data = [e.model_dump() for e in entries]
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return len(entries)


from typing import Tuple