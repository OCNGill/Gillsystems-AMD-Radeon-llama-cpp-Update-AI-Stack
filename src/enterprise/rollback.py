"""Rollback manager for Gillsystems AI Stack Updater Enterprise Edition.

Captures complete pre-update state snapshots and provides reversible updates.
Every mutating operation (ROCm install, llama.cpp build) creates a snapshot
that can be used to restore the previous state.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from pydantic import BaseModel, Field


class FileSnapshot(BaseModel):
    """Snapshot of a single file's state."""

    path: str
    size: int
    sha256: str
    exists: bool = True

    @classmethod
    def from_file(cls, filepath: Path) -> "FileSnapshot":
        """Create snapshot from existing file."""
        if not filepath.exists():
            return cls(path=str(filepath), size=0, sha256="", exists=False)

        stat = filepath.stat()
        sha256 = hashlib.sha256(filepath.read_bytes()).hexdigest()
        return cls(path=str(filepath), size=stat.st_size, sha256=sha256, exists=True)

    def verify(self, filepath: Path) -> bool:
        """Verify current file matches snapshot."""
        if not self.exists:
            return not filepath.exists()
        if not filepath.exists():
            return False
        return FileSnapshot.from_file(filepath).sha256 == self.sha256


class StateSnapshot(BaseModel):
    """Complete pre-update state snapshot for rollback."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    component: str  # rocm, llama.cpp, policy, etc.
    trigger: str  # update, build, config_change, etc.
    files: List[FileSnapshot] = Field(default_factory=list)
    config_snapshot: Optional[Dict[str, Any]] = None  # Full config at time of snapshot
    version_info: Optional[Dict[str, str]] = None  # installed versions at snapshot time
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_file(self, filepath: Path) -> None:
        """Add a file to the snapshot."""
        snapshot = FileSnapshot.from_file(filepath)
        # Avoid duplicates
        if not any(f.path == snapshot.path for f in self.files):
            self.files.append(snapshot)

    def add_config(self, config_dict: Dict[str, Any]) -> None:
        """Add configuration snapshot."""
        self.config_snapshot = config_dict

    def add_version_info(self, versions: Dict[str, str]) -> None:
        """Add version information."""
        self.version_info = versions


class RollbackManager:
    """Manages state snapshots and rollback operations."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS rollback_snapshots (
        id              TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        component       TEXT NOT NULL,
        trigger         TEXT NOT NULL,
        files_json      TEXT NOT NULL,
        config_json     TEXT,
        versions_json   TEXT,
        metadata_json   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_rollback_component ON rollback_snapshots(component);
    CREATE INDEX IF NOT EXISTS idx_rollback_timestamp ON rollback_snapshots(timestamp);
    """

    def __init__(self, db_path: Path, snapshot_dir: Optional[Path] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if snapshot_dir:
            self.snapshot_dir = Path(snapshot_dir)
        else:
            self.snapshot_dir = self.db_path.parent / "rollback_snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

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

    def create_snapshot(
        self,
        component: str,
        trigger: str,
        files_to_snapshot: List[Path],
        config: Optional[Dict[str, Any]] = None,
        versions: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StateSnapshot:
        """Create a new state snapshot before a mutating operation."""
        snapshot = StateSnapshot(
            component=component,
            trigger=trigger,
            metadata=metadata or {},
        )

        for fpath in files_to_snapshot:
            snapshot.add_file(fpath)

        if config:
            snapshot.add_config(config)

        if versions:
            snapshot.add_version_info(versions)

        # Persist to database
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO rollback_snapshots
                (id, timestamp, component, trigger, files_json, config_json, versions_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.timestamp,
                    snapshot.component,
                    snapshot.trigger,
                    json.dumps([f.model_dump() for f in snapshot.files]),
                    json.dumps(snapshot.config_snapshot) if snapshot.config_snapshot else None,
                    json.dumps(snapshot.version_info) if snapshot.version_info else None,
                    json.dumps(snapshot.metadata),
                ),
            )

        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Retrieve a snapshot by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM rollback_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if not row:
            return None

        return StateSnapshot(
            id=row["id"],
            timestamp=row["timestamp"],
            component=row["component"],
            trigger=row["trigger"],
            files=[FileSnapshot.model_validate(f) for f in json.loads(row["files_json"])],
            config_snapshot=json.loads(row["config_json"]) if row["config_json"] else None,
            version_info=json.loads(row["versions_json"]) if row["versions_json"] else None,
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    def get_latest_snapshot(self, component: str) -> Optional[StateSnapshot]:
        """Get the most recent snapshot for a component."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM rollback_snapshots WHERE component = ? ORDER BY rowid DESC LIMIT 1",
                (component,),
            ).fetchone()
        if not row:
            return None
        return self.get_snapshot(row["id"])

    def rollback(
        self,
        snapshot_id: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Rollback to a previous snapshot.

        Args:
            snapshot_id: ID of snapshot to restore
            dry_run: If True, only report what would be done

        Returns:
            Dict with rollback results: {"restored": [...], "failed": [...], "skipped": [...]}
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        results = {"restored": [], "failed": [], "skipped": []}

        for file_snap in snapshot.files:
            target_path = Path(file_snap.path)

            if dry_run:
                if file_snap.exists:
                    if target_path.exists():
                        if file_snap.verify(target_path):
                            results["skipped"].append(f"{file_snap.path} (already matches)")
                        else:
                            results["restored"].append(f"{file_snap.path} (would restore)")
                    else:
                        results["restored"].append(f"{file_snap.path} (would create)")
                else:
                    if target_path.exists():
                        results["restored"].append(f"{file_snap.path} (would delete)")
                    else:
                        results["skipped"].append(f"{file_snap.path} (already absent)")
                continue

            # Actual rollback
            try:
                if file_snap.exists:
                    # Restore file from snapshot directory (using filename only)
                    backup_name = Path(file_snap.path).name
                    backup_path = self.snapshot_dir / snapshot_id / backup_name
                    if backup_path.exists():
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup_path, target_path)
                        results["restored"].append(file_snap.path)
                    else:
                        # No backup stored — can't restore
                        results["failed"].append(f"{file_snap.path} (no backup stored)")
                else:
                    # File didn't exist at snapshot time — delete if present
                    if target_path.exists():
                        target_path.unlink()
                        results["restored"].append(f"{file_snap.path} (deleted)")
                    else:
                        results["skipped"].append(f"{file_snap.path} (already absent)")
            except Exception as e:
                results["failed"].append(f"{file_snap.path} ({e})")

        return results

    def list_snapshots(
        self,
        component: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List available snapshots."""
        query = "SELECT id, timestamp, component, trigger FROM rollback_snapshots"
        params: List[Any] = []

        if component:
            query += " WHERE component = ?"
            params.append(component)

        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(r) for r in rows]

    def store_file_backups(self, snapshot_id: str, files: List[Path]) -> int:
        """Store backup copies of files for later rollback (call before mutation)."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        stored = 0
        for fpath in files:
            if fpath.exists():
                # Use just the filename for backup storage to avoid path issues
                backup_name = fpath.name
                backup_path = self.snapshot_dir / snapshot_id / backup_name
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fpath, backup_path)
                stored += 1

        return stored


def create_pre_update_snapshot(
    rollback_mgr: RollbackManager,
    component: str,
    files: List[Path],
    config: Optional[Dict[str, Any]] = None,
    versions: Optional[Dict[str, str]] = None,
) -> StateSnapshot:
    """Convenience function to create snapshot and store file backups."""
    snapshot = rollback_mgr.create_snapshot(
        component=component,
        trigger="update",
        files_to_snapshot=files,
        config=config,
        versions=versions,
    )
    # Store actual file backups for rollback
    rollback_mgr.store_file_backups(snapshot.id, files)
    return snapshot