"""Start and stop the remote llama.cpp router through a restricted SSH key."""
import os
import shutil
import subprocess
from pathlib import Path


class LLMServerLifecycle:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", False))
        self.host = str(self.cfg.get("host", "")).strip()
        self.port = max(1, min(65535, int(self.cfg.get("port", 22))))
        self.user = str(self.cfg.get("user", "")).strip()
        raw_key = self.cfg.get("key_path") or "~/.ssh/id_ed25519"
        self.key_path = Path(os.path.expandvars(str(raw_key))).expanduser()
        self.start_timeout = max(30, int(self.cfg.get("start_timeout", 190)))
        self.stop_timeout = max(10, int(self.cfg.get("stop_timeout", 45)))

    def _run(self, action, timeout):
        if not self.enabled:
            return "DISABLED"
        if not self.host or not self.user:
            raise RuntimeError("Remote LLM lifecycle requires llm_lifecycle.host and llm_lifecycle.user")
        ssh = shutil.which("ssh")
        if not ssh:
            raise RuntimeError("OpenSSH client was not found on PATH")
        if not self.key_path.is_file():
            raise RuntimeError(f"SSH key not found: {self.key_path}")
        remote_command = str(self.cfg.get(f"{action}_command") or action).strip()
        if not remote_command:
            raise RuntimeError(f"Remote LLM {action} command cannot be empty")
        password = str(self.cfg.get("password", ""))
        if password:
            return self._run_with_password(remote_command, timeout, password)
        command = [
            ssh, "-i", str(self.key_path), "-o", "IdentitiesOnly=yes",
            "-p", str(self.port),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", f"ConnectTimeout={min(15, timeout)}",
            f"{self.user}@{self.host}", remote_command,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Remote LLM {action} timed out after {timeout}s") from exc
        except OSError as exc:
            raise RuntimeError(f"Could not run SSH: {exc}") from exc
        output = (result.stdout or "").strip()
        if result.returncode:
            detail = (result.stderr or output or f"ssh exit code {result.returncode}").strip()
            raise RuntimeError(f"Remote LLM {action} failed: {detail[:1000]}")
        return output or "OK"

    def _run_with_password(self, remote_command, timeout, password):
        """Run an SSH command with password/key-passphrase auth and strict host keys."""
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("Password-based SSH requires Paramiko. Install project requirements.") from exc
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=self.host, port=self.port, username=self.user, password=password,
                key_filename=str(self.key_path) if self.key_path.is_file() else None,
                timeout=min(15, timeout), banner_timeout=min(15, timeout),
                auth_timeout=min(15, timeout), allow_agent=False, look_for_keys=False,
            )
            _, stdout, stderr = client.exec_command(remote_command, timeout=timeout)
            status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            if status:
                raise RuntimeError(f"Remote SSH command failed: {(error or output or status)[:1000]}")
            return output or "OK"
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Could not run password-authenticated SSH: {exc}") from exc
        finally:
            client.close()

    def start(self):
        result = self._run("start", self.start_timeout)
        if result not in ("STARTED", "RUNNING"):
            raise RuntimeError(f"Unexpected response from remote LLM start: {result[:500]}")
        return result

    def stop(self):
        result = self._run("stop", self.stop_timeout)
        if result != "STOPPED":
            raise RuntimeError(f"Unexpected response from remote LLM stop: {result[:500]}")
        return result

    def status(self):
        result = self._run("status", min(20, self.stop_timeout))
        if result not in ("RUNNING", "RUNNING_UNMANAGED", "STOPPED"):
            raise RuntimeError(f"Unexpected response from remote LLM status: {result[:500]}")
        return result
