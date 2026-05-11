"""Tests for gateway runtime status tracking."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

from gateway import status


class TestGatewayPidState:
    def test_write_pid_file_records_gateway_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        status.write_pid_file()

        payload = json.loads((tmp_path / "gateway.pid").read_text())
        assert payload["pid"] == os.getpid()
        assert payload["kind"] == "hermes-gateway"
        assert isinstance(payload["argv"], list)
        assert payload["argv"]

    def test_write_pid_file_is_atomic_against_concurrent_writers(self, tmp_path, monkeypatch):
        """Regression: two concurrent --replace invocations must not both win.

        Without O_CREAT|O_EXCL, two processes racing through start_gateway()'s
        termination-wait would both write to gateway.pid, silently overwriting
        each other and leaving multiple gateway instances alive (#11718).
        """
        import pytest

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        # First write wins.
        status.write_pid_file()
        assert (tmp_path / "gateway.pid").exists()

        # Second write (simulating a racing --replace that missed the earlier
        # guards) must raise FileExistsError rather than clobber the record.
        with pytest.raises(FileExistsError):
            status.write_pid_file()

        # Original record is preserved.
        payload = json.loads((tmp_path / "gateway.pid").read_text())
        assert payload["pid"] == os.getpid()

    def test_get_running_pid_rejects_live_non_gateway_pid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        pid_path.write_text(str(os.getpid()))

        assert status.get_running_pid() is None
        assert not pid_path.exists()

    def test_get_running_pid_cleans_stale_record_from_dead_process(self, tmp_path, monkeypatch):
        # Simulates the aftermath of a crash: the PID file still points at a
        # process that no longer exists. The next gateway startup must be
        # able to unlink it so ``write_pid_file``'s O_EXCL create succeeds —
        # otherwise systemd's restart loop hits "PID file race lost" forever.
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        dead_pid = 999999  # not our pid, and below we simulate it's dead
        pid_path.write_text(json.dumps({
            "pid": dead_pid,
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway", "run"],
            "start_time": 111,
        }))

        def _dead_process(pid, sig):
            raise ProcessLookupError

        monkeypatch.setattr(status.os, "kill", _dead_process)

        assert status.get_running_pid() is None
        assert not pid_path.exists()

    def test_get_running_pid_accepts_gateway_metadata_when_cmdline_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        pid_path.write_text(json.dumps({
            "pid": os.getpid(),
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))

        monkeypatch.setattr(status.os, "kill", lambda pid, sig: None)
        monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 123)
        monkeypatch.setattr(status, "_read_process_cmdline", lambda pid: None)

        assert status.acquire_gateway_runtime_lock() is True
        try:
            assert status.get_running_pid() == os.getpid()
        finally:
            status.release_gateway_runtime_lock()

    def test_get_running_pid_accepts_script_style_gateway_cmdline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        pid_path.write_text(json.dumps({
            "pid": os.getpid(),
            "kind": "hermes-gateway",
            "argv": ["/venv/bin/python", "/repo/hermes_cli/main.py", "gateway", "run", "--replace"],
            "start_time": 123,
        }))

        monkeypatch.setattr(status.os, "kill", lambda pid, sig: None)
        monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 123)
        monkeypatch.setattr(
            status,
            "_read_process_cmdline",
            lambda pid: "/venv/bin/python /repo/hermes_cli/main.py gateway run --replace",
        )

        assert status.acquire_gateway_runtime_lock() is True
        try:
            assert status.get_running_pid() == os.getpid()
        finally:
            status.release_gateway_runtime_lock()

    def test_get_running_pid_accepts_explicit_pid_path_without_cleanup(self, tmp_path, monkeypatch):
        other_home = tmp_path / "profile-home"
        other_home.mkdir()
        pid_path = other_home / "gateway.pid"
        pid_path.write_text(json.dumps({
            "pid": os.getpid(),
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))

        monkeypatch.setattr(status.os, "kill", lambda pid, sig: None)
        monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 123)
        monkeypatch.setattr(status, "_read_process_cmdline", lambda pid: None)

        lock_path = other_home / "gateway.lock"
        lock_path.write_text(json.dumps({
            "pid": os.getpid(),
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))
        monkeypatch.setattr(status, "is_gateway_runtime_lock_active", lambda lock_path=None: True)

        assert status.get_running_pid(pid_path, cleanup_stale=False) == os.getpid()
        assert pid_path.exists()

    def test_runtime_lock_claims_and_releases_liveness(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        assert status.is_gateway_runtime_lock_active() is False
        assert status.acquire_gateway_runtime_lock() is True
        assert status.is_gateway_runtime_lock_active() is True

        status.release_gateway_runtime_lock()

        assert status.is_gateway_runtime_lock_active() is False

    def test_get_running_pid_treats_pid_file_as_stale_without_runtime_lock(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        pid_path.write_text(json.dumps({
            "pid": os.getpid(),
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))

        monkeypatch.setattr(status.os, "kill", lambda pid, sig: None)
        monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 123)
        monkeypatch.setattr(status, "_read_process_cmdline", lambda pid: None)

        assert status.get_running_pid() is None
        assert not pid_path.exists()

    def test_get_running_pid_cleans_stale_metadata_from_dead_foreign_pid(self, tmp_path, monkeypatch):
        """Stale PID file from a *different* PID (crashed process) must still be cleaned.

        Regression for: ``remove_pid_file()`` defensively refuses to delete a
        PID file whose pid != ``os.getpid()`` to protect ``--replace``
        handoffs.  Stale-cleanup must not go through that path or real
        crashed-process PID files never get removed.
        """
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        lock_path = tmp_path / "gateway.lock"

        # PID that is guaranteed not alive and not our own.
        dead_foreign_pid = 999999
        assert dead_foreign_pid != os.getpid()

        pid_path.write_text(json.dumps({
            "pid": dead_foreign_pid,
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))
        lock_path.write_text(json.dumps({
            "pid": dead_foreign_pid,
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))

        # No live lock holder → get_running_pid should clean both files.
        assert status.get_running_pid() is None
        assert not pid_path.exists()
        assert not lock_path.exists()

    def test_get_running_pid_falls_back_to_live_lock_record(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        pid_path = tmp_path / "gateway.pid"
        pid_path.write_text(json.dumps({
            "pid": 99999,
            "kind": "hermes-gateway",
            "argv": ["python", "-m", "hermes_cli.main", "gateway"],
            "start_time": 123,
        }))

        monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 123)
        monkeypatch.setattr(status, "_read_process_cmdline", lambda pid: None)
        monkeypatch.setattr(
            status,
            "_build_pid_record",
            lambda: {
                "pid": os.getpid(),
                "kind": "hermes-gateway",
                "argv": ["python", "-m", "hermes_cli.main", "gateway"],
                "start_time": 123,
            },
        )
        assert status.acquire_gateway_runtime_lock() is True

        def fake_kill(pid, sig):
            if pid == 99999:
                raise ProcessLookupError
            return None

        monkeypatch.setattr(status.os, "kill", fake_kill)

        try:
            assert status.get_running_pid() == os.getpid()
        finally:
            status.release_gateway_runtime_lock()


class TestGatewayRuntimeStatus:
    def test_write_json_file_uses_atomic_json_write(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        calls = []

        def _fake_atomic_json_write(path, payload, **kwargs):
            calls.append((Path(path), payload, kwargs))

        monkeypatch.setattr(status, "atomic_json_write", _fake_atomic_json_write)

        payload = {"gateway_state": "running"}
        target = tmp_path / "gateway_state.json"
        status._write_json_file(target, payload)

        assert calls == [
            (
                target,
                payload,
                {"indent": None, "separators": (",", ":")},
            )
        ]

    def test_write_runtime_status_overwrites_stale_pid_on_restart(self, tmp_path, monkeypatch):
        """Regression: setdefault() preserved stale PID from previous process (#1631)."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        # Simulate a previous gateway run that left a state file with a stale PID
        state_path = tmp_path / "gateway_state.json"
        state_path.write_text(json.dumps({
            "pid": 99999,
            "start_time": 1000.0,
            "kind": "hermes-gateway",
            "platforms": {},
            "updated_at": "2025-01-01T00:00:00Z",
        }))

        status.write_runtime_status(gateway_state="running")

        payload = status.read_runtime_status()
        assert payload["pid"] == os.getpid(), "PID should be overwritten, not preserved via setdefault"
        assert payload["start_time"] != 1000.0, "start_time should be overwritten on restart"

    def test_write_runtime_status_records_platform_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        status.write_runtime_status(
            gateway_state="startup_failed",
            exit_reason="telegram conflict",
            platform="telegram",
            platform_state="fatal",
            error_code="telegram_polling_conflict",
            error_message="another poller is active",
        )

        payload = status.read_runtime_status()
        assert payload["gateway_state"] == "startup_failed"
        assert payload["exit_reason"] == "telegram conflict"
        assert payload["platforms"]["telegram"]["state"] == "fatal"
        assert payload["platforms"]["telegram"]["error_code"] == "telegram_polling_conflict"
        assert payload["platforms"]["telegram"]["error_message"] == "another poller is active"

    def test_write_runtime_status_explicit_none_clears_stale_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        status.write_runtime_status(
            gateway_state="startup_failed",
            exit_reason="stale error",
            platform="discord",
            platform_state="fatal",
            error_code="discord_timeout",
            error_message="stale platform error",
        )

        status.write_runtime_status(
            gateway_state="running",
            exit_reason=None,
            platform="discord",
            platform_state="connected",
            error_code=None,
            error_message=None,
        )

        payload = status.read_runtime_status()
        assert payload["gateway_state"] == "running"
        assert payload["exit_reason"] is None
        assert payload["platforms"]["discord"]["state"] == "connected"
        assert payload["platforms"]["discord"]["error_code"] is None
        assert payload["platforms"]["discord"]["error_message"] is None


class TestTerminatePid:
    def test_force_uses_taskkill_on_windows(self, monkeypatch):
        calls = []
        monkeypatch.setattr(status, "_IS_WINDOWS", True)

        def fake_run(cmd, capture_output=False, text=False, timeout=None):
            calls.append((cmd, capture_output, text, timeout))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(status.subprocess, "run", fake_run)

        status.terminate_pid(123, force=True)

        assert calls == [
            (["taskkill", "/PID", "123", "/T", "/F"], True, True, 10)
        ]

    def test_force_falls_back_to_sigterm_when_taskkill_missing(self, monkeypatch):
        calls = []
        monkeypatch.setattr(status, "_IS_WINDOWS", True)

        def fake_run(*args, **kwargs):
            raise FileNotFoundError

        def fake_kill(pid, sig):
            calls.append((pid, sig))

        monkeypatch.setattr(status.subprocess, "run", fake_run)
        monkeypatch.setattr(status.os, "kill", fake_kill)

        status.terminate_pid(456, force=True)

        assert calls == [(456, status.signal.SIGTERM)]


class TestScopedLocks:
    def test_windows_file_lock_uses_high_offset(self, tmp_path, monkeypatch):
        lock_path = tmp_path / "gateway.lock"
        handle = open(lock_path, "a+", encoding="utf-8")
        fd = handle.fileno()
        calls = []

        def fake_locking(fd, mode, size):
            calls.append((fd, mode, size, handle.tell()))

        monkeypatch.setattr(status, "_IS_WINDOWS", True)
        monkeypatch.setattr(
            status,
            "msvcrt",
            SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=fake_locking),
            raising=False,
        )

        try:
            assert status._try_acquire_file_lock(handle) is True
            status._release_file_lock(handle)
        finally:
            handle.close()

        assert calls == [
            (fd, 1, 1, status._WINDOWS_LOCK_OFFSET),
            (fd, 2, 1, status._WINDOWS_LOCK_OFFSET),
        ]
