"""Offline repository validation plus bounded local/live HTTP smoke checks."""

from __future__ import annotations

import json
import os
import secrets
import shlex
import socket
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .manifest import Check, Manifest


class ConformanceError(RuntimeError):
    """A repository or deployed application violated its manifest."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    id: str
    category: str
    status: int
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class Report:
    template: str
    source_ref: str
    base_url: str
    checked_at: str
    deployment_id: str | None
    deployment_status: str | None
    results: tuple[CheckResult, ...]


def validate_repository(manifest: Manifest, repo: str | Path) -> None:
    """Validate source/config invariants without starting or networking."""

    root = Path(repo).resolve()
    required_files = (
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "railway.json",
        "uv.lock",
    )
    missing = [name for name in required_files if not (root / name).is_file()]
    if missing:
        raise ConformanceError(f"repository is missing required files: {missing}")
    railway = json.loads((root / "railway.json").read_text(encoding="utf-8"))
    deploy = railway.get("deploy", {})
    if deploy.get("startCommand") != manifest.start_command:
        raise ConformanceError("railway.json startCommand does not match the manifest")
    if deploy.get("healthcheckPath") != manifest.health_path:
        raise ConformanceError("railway.json healthcheckPath does not match the manifest")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project.get("project", {}).get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ConformanceError("project.dependencies must be a list")
    chirp_dependencies = [
        str(value) for value in dependencies if str(value).startswith("bengal-chirp")
    ]
    if len(chirp_dependencies) != 1:
        raise ConformanceError("project must declare exactly one bengal-chirp dependency")
    if "git+" in chirp_dependencies[0]:
        raise ConformanceError("starter must depend on a released Chirp version")
    command = shlex.split(manifest.start_command)
    if (
        len(command) >= 2
        and command[0].endswith("python")
        and command[1].endswith(".py")
        and not (root / command[1]).is_file()
    ):
        raise ConformanceError(f"start entrypoint does not exist: {command[1]}")


def _request(base_url: str, check: Check, timeout: float) -> CheckResult:
    url = f"{base_url.rstrip('/')}{check.path}"
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ConformanceError(f"{check.id} URL must use http or https")
    headers = dict(check.request_headers)
    body = check.body.encode() if check.body is not None else None
    # The scheme is restricted above; urllib cannot open file/custom protocols.
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers=headers, method=check.method
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = response.status
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            if check.stream:
                chunks: list[bytes] = []
                for _ in range(32):
                    line = response.readline(4096)
                    if not line:
                        break
                    chunks.append(line)
                    text = b"".join(chunks).decode("utf-8", "replace")
                    if check.contains and all(value in text for value in check.contains):
                        break
                payload = b"".join(chunks).decode("utf-8", "replace")
            else:
                payload = response.read(256 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        payload = exc.read(256 * 1024).decode("utf-8", "replace")
    except OSError as exc:
        raise ConformanceError(f"{check.id} request failed: {exc}") from exc
    if status != check.status:
        raise ConformanceError(f"{check.id} expected HTTP {check.status}, got {status}")
    for key, value in check.headers:
        actual = response_headers.get(key.lower(), "")
        if value.lower() not in actual.lower():
            raise ConformanceError(
                f"{check.id} expected header {key} to contain {value!r}, got {actual!r}"
            )
    for value in check.contains:
        if value not in payload:
            raise ConformanceError(f"{check.id} response did not contain {value!r}")
    return CheckResult(check.id, check.category, status, round((time.monotonic() - started) * 1000))


def run_smoke(
    manifest: Manifest,
    base_url: str,
    *,
    timeout: float = 10.0,
    deployment_id: str | None = None,
    deployment_status: str | None = None,
) -> Report:
    """Run every declared HTTP contract against an existing deployment."""

    if deployment_status is not None and deployment_status != "SUCCESS":
        raise ConformanceError(f"deployment is not terminal-successful: {deployment_status}")
    results = tuple(_request(base_url, check, timeout) for check in manifest.checks)
    return Report(
        template=manifest.slug,
        source_ref=manifest.ref,
        base_url=base_url,
        checked_at=datetime.now(UTC).isoformat(),
        deployment_id=deployment_id,
        deployment_status=deployment_status,
        results=results,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _local_command(root: Path, start_command: str) -> list[str]:
    """Resolve a generic Railway command inside the starter's own environment."""

    command = shlex.split(start_command)
    if not command or command[0] not in {"python", "python3"}:
        return command
    candidates = (
        root / ".venv" / "bin" / command[0],
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
    )
    interpreter = next((candidate for candidate in candidates if candidate.is_file()), None)
    if interpreter is None:
        raise ConformanceError(
            "starter virtual environment is missing; run `uv sync --frozen` "
            "before local conformance"
        )
    return [str(interpreter), *command[1:]]


def _wait_ready(url: str, process: subprocess.Popen[Any], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ConformanceError(
                f"production command exited before readiness with {process.returncode}"
            )
        try:
            # run_local constructs this loopback HTTP URL itself.
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except OSError as exc:
            last_error = str(exc)
        time.sleep(0.1)
    raise ConformanceError(f"readiness timed out: {last_error}")


def run_local(
    manifest: Manifest,
    repo: str | Path,
    *,
    port: int | None = None,
    startup_timeout: float = 30.0,
    request_timeout: float = 10.0,
) -> Report:
    """Start the production command, smoke it, and terminate it cleanly."""

    root = Path(repo).resolve()
    validate_repository(manifest, root)
    selected_port = port or _free_port()
    base_url = f"http://127.0.0.1:{selected_port}"
    env = {
        **os.environ,
        "CHIRP_DEBUG": "0",
        "CHIRP_ENV": "production",
        "CHIRP_HOST": "127.0.0.1",
        "CHIRP_PORT": str(selected_port),
        "CHIRP_SECRET_KEY": secrets.token_urlsafe(32),
        "PORT": str(selected_port),
    }
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log:
        # The reviewed repository manifest intentionally owns its production command.
        process = subprocess.Popen(  # noqa: S603
            _local_command(root, manifest.start_command),
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_ready(f"{base_url}{manifest.health_path}", process, startup_timeout)
            return run_smoke(manifest, base_url, timeout=request_timeout)
        except Exception as exc:
            log.seek(0)
            output = log.read()[-8000:]
            raise ConformanceError(f"{exc}\n--- production log ---\n{output}") from exc
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def report_dict(report: Report) -> dict[str, Any]:
    """Return a JSON-safe evidence representation."""

    return {
        "template": report.template,
        "source_ref": report.source_ref,
        "base_url": report.base_url,
        "checked_at": report.checked_at,
        "deployment_id": report.deployment_id,
        "deployment_status": report.deployment_status,
        "results": [asdict(result) for result in report.results],
    }
