"""Tests for enterprise audit log module."""
import pytest
import tempfile
from pathlib import Path
from src.enterprise.audit import AuditEntry, AuditLog


def test_audit_entry_hash():
    entry = AuditEntry(
        actor="test-user",
        action="update_rocm",
        component="rocm",
        old_version="6.1.0",
        new_version="6.2.0",
    )
    hash1 = entry.compute_hash()
    assert len(hash1) == 64  # SHA256 hex

    # Same content = same hash
    entry2 = AuditEntry(
        actor="test-user",
        action="update_rocm",
        component="rocm",
        old_version="6.1.0",
        new_version="6.2.0",
    )
    assert entry2.compute_hash() == hash1

    # Different content = different hash
    entry3 = AuditEntry(
        actor="test-user",
        action="update_rocm",
        component="rocm",
        old_version="6.1.0",
        new_version="6.2.1",  # Different
    )
    assert entry3.compute_hash() != hash1


def test_audit_entry_seal_and_verify():
    entry = AuditEntry(
        actor="test-user",
        action="update_rocm",
        component="rocm",
    ).seal("previous_hash_123")

    assert entry.prev_hash == "previous_hash_123"
    assert entry.hash == entry.compute_hash()
    assert entry.verify("previous_hash_123") is True
    assert entry.verify("wrong_hash") is False


def test_audit_log_append_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.db"
        log = AuditLog(db_path)

        entry = log.append(
            actor="user1",
            action="update_rocm",
            component="rocm",
            old_version="6.1.0",
            new_version="6.2.0",
            policy_decision={"allowed": True, "reason": "Allowed by policy"},
            approval={"request_id": "req-123", "approver": "admin@example.com", "timestamp": "2026-10-02T00:00:00Z"},
        )

        assert entry.id is not None
        assert entry.actor == "user1"
        assert entry.action == "update_rocm"
        assert entry.component == "rocm"
        assert entry.prev_hash == ""  # First entry (genesis)
        assert entry.hash == entry.compute_hash()

        # Retrieve
        retrieved = log.get_entry(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.hash == entry.hash
        
        log.close()


def test_audit_log_chain_integrity():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.db"
        log = AuditLog(db_path)

        # Add multiple entries
        e1 = log.append(actor="u1", action="a1", component="c1")
        e2 = log.append(actor="u2", action="a2", component="c2")
        e3 = log.append(actor="u3", action="a3", component="c3")

        # Verify chain
        valid, errors = log.verify_chain()
        assert valid is True
        assert errors == []

        # Check hash chain links
        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash
        
        log.close()


def test_audit_log_query_filters():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.db"
        log = AuditLog(db_path)

        log.append(actor="alice", action="update", component="rocm")
        log.append(actor="bob", action="update", component="llama.cpp")
        log.append(actor="alice", action="rollback", component="rocm")
        log.append(actor="charlie", action="policy_change", component="policy")

        # Filter by actor
        alice_entries = log.get_entries(actor="alice")
        assert len(alice_entries) == 2
        assert all(e.actor == "alice" for e in alice_entries)

        # Filter by component
        rocm_entries = log.get_entries(component="rocm")
        assert len(rocm_entries) == 2
        assert all(e.component == "rocm" for e in rocm_entries)

        # Filter by action
        update_entries = log.get_entries(action="update")
        assert len(update_entries) == 2
        assert all(e.action == "update" for e in update_entries)
        
        log.close()


def test_audit_log_tamper_detection():
    """Direct DB tampering should be detected by verify_chain."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.db"
        log = AuditLog(db_path)

        e1 = log.append(actor="u1", action="a1", component="c1")
        e2 = log.append(actor="u2", action="a2", component="c2")

        log.close()  # Close before direct DB access

        # Tamper with the database directly
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE audit_log SET actor = 'hacker' WHERE id = ?", (e1.id,))
        conn.commit()
        conn.close()

        # Reopen log for verification
        log2 = AuditLog(db_path)
        # Chain verification should detect tampering
        valid, errors = log2.verify_chain()
        assert valid is False
        assert len(errors) > 0
        assert "Chain break" in errors[0] or "hash mismatch" in errors[0]
        
        log2.close()


def test_audit_log_export_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit.db"
        log = AuditLog(db_path)

        log.append(actor="u1", action="a1", component="c1")
        log.append(actor="u2", action="a2", component="c2")

        export_path = Path(tmpdir) / "audit_export.json"
        count = log.export_json(export_path)

        assert count == 2
        assert export_path.exists()

        import json
        data = json.loads(export_path.read_text())
        assert len(data) == 2
        # Entries returned in DESC order (newest first)
        assert data[0]["actor"] == "u2"
        assert data[1]["actor"] == "u1"

        log.close()