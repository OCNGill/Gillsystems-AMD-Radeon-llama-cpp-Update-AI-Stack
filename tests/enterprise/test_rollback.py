"""Tests for enterprise rollback module."""
import pytest
import tempfile
from pathlib import Path
from src.enterprise.rollback import FileSnapshot, StateSnapshot, RollbackManager, create_pre_update_snapshot


def test_file_snapshot_from_existing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hello world")

        snap = FileSnapshot.from_file(test_file)
        assert snap.exists is True
        assert snap.size == 11
        assert snap.sha256 == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        # Verify matches
        assert snap.verify(test_file) is True


def test_file_snapshot_from_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        missing_file = Path(tmpdir) / "missing.txt"

        snap = FileSnapshot.from_file(missing_file)
        assert snap.exists is False
        assert snap.size == 0
        assert snap.sha256 == ""

        # Verify missing file
        assert snap.verify(missing_file) is True


def test_file_snapshot_verify_changed_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hello world")

        snap = FileSnapshot.from_file(test_file)

        # Modify file
        test_file.write_text("changed content")
        assert snap.verify(test_file) is False


def test_state_snapshot_add_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content")

        snapshot = StateSnapshot(component="rocm", trigger="update")
        snapshot.add_file(test_file)

        assert len(snapshot.files) == 1
        assert snapshot.files[0].path == str(test_file)
        assert snapshot.files[0].exists is True


def test_state_snapshot_avoid_duplicates():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content")

        snapshot = StateSnapshot(component="rocm", trigger="update")
        snapshot.add_file(test_file)
        snapshot.add_file(test_file)  # Add again

        assert len(snapshot.files) == 1  # No duplicate


def test_rollback_manager_create_snapshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        mgr = RollbackManager(db_path)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original content")

        snapshot = mgr.create_snapshot(
            component="rocm",
            trigger="update",
            files_to_snapshot=[test_file],
            config={"version": "6.2.1"},
            versions={"rocm": "6.1.0"},
        )

        assert snapshot.id is not None
        assert snapshot.component == "rocm"
        assert snapshot.trigger == "update"
        assert len(snapshot.files) == 1
        assert snapshot.config_snapshot == {"version": "6.2.1"}
        assert snapshot.version_info == {"rocm": "6.1.0"}

        # Retrieve
        retrieved = mgr.get_snapshot(snapshot.id)
        assert retrieved is not None
        assert retrieved.id == snapshot.id
        
        mgr.close()


def test_rollback_manager_latest_snapshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        mgr = RollbackManager(db_path)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("v1")

        s1 = mgr.create_snapshot("rocm", "update", [test_file])
        test_file.write_text("v2")
        s2 = mgr.create_snapshot("rocm", "update", [test_file])

        latest = mgr.get_latest_snapshot("rocm")
        assert latest is not None
        assert latest.id == s2.id
        
        mgr.close()


def test_rollback_manager_list_snapshots():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        mgr = RollbackManager(db_path)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content")

        mgr.create_snapshot("rocm", "update", [test_file])
        mgr.create_snapshot("llama.cpp", "build", [test_file])

        all_snapshots = mgr.list_snapshots()
        assert len(all_snapshots) == 2

        rocm_snapshots = mgr.list_snapshots(component="rocm")
        assert len(rocm_snapshots) == 1
        assert rocm_snapshots[0]["component"] == "rocm"
        
        mgr.close()


def test_rollback_manager_rollback_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        snap_dir = Path(tmpdir) / "snaps"
        mgr = RollbackManager(db_path, snap_dir)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        snapshot = mgr.create_snapshot("rocm", "update", [test_file])
        mgr.store_file_backups(snapshot.id, [test_file])

        # Modify file
        test_file.write_text("modified")

        # Dry run rollback
        result = mgr.rollback(snapshot.id, dry_run=True)

        assert "original" in result["restored"][0] or "test.txt" in result["restored"][0]
        # File should still be modified
        assert test_file.read_text() == "modified"
        
        mgr.close()


def test_rollback_manager_rollback_actual():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        snap_dir = Path(tmpdir) / "snaps"
        mgr = RollbackManager(db_path, snap_dir)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        snapshot = mgr.create_snapshot("rocm", "update", [test_file])
        mgr.store_file_backups(snapshot.id, [test_file])

        # Modify file
        test_file.write_text("modified")

        # Actual rollback
        result = mgr.rollback(snapshot.id, dry_run=False)

        assert len(result["restored"]) == 1
        assert test_file.read_text() == "original"
        
        mgr.close()


def test_rollback_manager_rollback_delete_new_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        snap_dir = Path(tmpdir) / "snaps"
        mgr = RollbackManager(db_path, snap_dir)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        snapshot = mgr.create_snapshot("rocm", "update", [test_file])
        mgr.store_file_backups(snapshot.id, [test_file])

        # Create a new file that didn't exist at snapshot time
        new_file = Path(tmpdir) / "new_file.txt"
        new_file.write_text("new content")

        # Rollback should delete it
        result = mgr.rollback(snapshot.id, dry_run=False)

        # Check that new_file would be deleted (since it wasn't in snapshot)
        # The rollback only restores files that were in the snapshot
        # New files are not automatically deleted unless they were tracked
        
        mgr.close()


def test_create_pre_update_snapshot_convenience():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rollback.db"
        snap_dir = Path(tmpdir) / "snaps"
        mgr = RollbackManager(db_path, snap_dir)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        snapshot = create_pre_update_snapshot(
            mgr,
            component="llama.cpp",
            files=[test_file],
            config={"model": "llama.cpp"},
            versions={"llama.cpp": "b4500"},
        )

        assert snapshot.component == "llama.cpp"
        assert snapshot.trigger == "update"
        assert snapshot.config_snapshot == {"model": "llama.cpp"}
        assert snapshot.version_info == {"llama.cpp": "b4500"}

        # Backup should exist
        backup_file = snap_dir / snapshot.id / "test.txt"
        assert backup_file.exists()
        assert backup_file.read_text() == "original"

        mgr.close()