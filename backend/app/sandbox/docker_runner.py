"""Opt-in Docker sandbox for bounded, untrusted Python snippets.

The image must already exist locally: --pull=never prevents implicit network pulls.
The container has no network, no capabilities, a read-only rootfs, strict limits,
and receives only a read-only temporary source directory.
"""
import os
import subprocess
import tempfile
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """Raised when sandbox execution is disabled or Docker is unavailable."""


def execute_python(source: str, timeout_seconds: int = 15) -> dict[str, object]:
    if os.getenv("APP_ENABLE_SANDBOX", "false").lower() != "true":
        raise SandboxUnavailable("Sandbox execution is disabled by configuration")
    if len(source.encode()) > 32_000:
        raise ValueError("Source exceeds the 32 KB sandbox limit")
    if not 1 <= timeout_seconds <= 20:
        raise ValueError("Timeout must be between 1 and 20 seconds")
    with tempfile.TemporaryDirectory(prefix="appforge-sandbox-") as temp_dir:
        source_path = Path(temp_dir) / "main.py"
        source_path.write_text(source, encoding="utf-8")
        source_path.chmod(0o444)
        command = [
            "docker", "run", "--rm", "--pull=never",
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--memory=256m", "--cpus=1",
            "--pids-limit=64", "--user=65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--mount", f"type=bind,src={temp_dir},dst=/workspace,readonly",
            "--workdir", "/workspace", "python:3.12-alpine",
            "python", "-I", "/workspace/main.py",
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout_seconds, check=False
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable("Docker CLI is not installed") from exc
        except subprocess.TimeoutExpired:
            return {"status": "timed_out", "stdout": "", "stderr": "Execution time limit exceeded"}
        return {
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-8000:],
        }
