from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from chirp_railway_conformance import (
    ConformanceError,
    ManifestError,
    load_manifest,
    run_local,
    validate_operations,
    validate_repository,
)


def _manifest(repo: Path, *, required: list[str] | None = None) -> Path:
    path = repo / "railway-template.json"
    categories = required or ["full-page", "readiness"]
    checks = []
    if "full-page" in categories:
        checks.append(
            {
                "id": "home",
                "category": "full-page",
                "path": "/",
                "contains": ["hello"],
            }
        )
    if "readiness" in categories:
        checks.append(
            {
                "id": "ready",
                "category": "readiness",
                "path": "/ready",
                "contains": ["ready"],
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "template": {
                    "slug": "fixture",
                    "title": "Fixture",
                    "repository": "https://github.com/example/fixture",
                    "ref": "abc123",
                    "python": "3.14",
                    "chirp_spec": ">=0.10,<0.11",
                    "chirp_locked": "0.10.0",
                    "start_command": f"{sys.executable} app.py",
                    "health_path": "/ready",
                    "owner": "fixture-owner",
                    "support_url": "https://github.com/example/fixture/issues",
                    "status": "draft",
                    "public_url": None,
                    "demo_url": None,
                    "last_successful_smoke": None,
                    "services": ["app"],
                    "variables": [
                        {"name": "CHIRP_ENV", "source": "template", "secret": False},
                        {"name": "CHIRP_SECRET_KEY", "source": "railway", "secret": True},
                        {"name": "CHIRP_ADMIN_TOKEN", "source": "template", "secret": True},
                    ],
                },
                "required_categories": categories,
                "required_operations": [
                    "deployment",
                    "ejection",
                    "restart",
                    "rollback",
                    "shutdown",
                    "update",
                ],
                "checks": checks,
            }
        ),
        encoding="utf-8",
    )
    return path


def _repo(tmp_path: Path) -> Path:
    for name in ("CHANGELOG.md", "LICENSE", "README.md", "uv.lock"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.14\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.1.0"\ndependencies=["bengal-chirp>=0.10,<0.11"]\n',
        encoding="utf-8",
    )
    (tmp_path / "railway.json").write_text(
        json.dumps(
            {
                "build": {"builder": "RAILPACK"},
                "deploy": {
                    "startCommand": f"{sys.executable} app.py",
                    "healthcheckPath": "/ready",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        """\
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ready":
            body = b"ready"
        elif os.environ.get("CHIRP_ADMIN_TOKEN"):
            body = b"hello template-secret-set"
        else:
            body = b"hello template-secret-missing"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

ThreadingHTTPServer(("127.0.0.1", int(os.environ["CHIRP_PORT"])), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.issue(737)
def test_manifest_and_repository_validate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest = load_manifest(_manifest(repo))
    validate_repository(manifest, repo)
    assert manifest.required_user_variables == ()


@pytest.mark.issue(737)
def test_manifest_rejects_missing_required_category(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _manifest(repo)
    raw = json.loads(path.read_text())
    raw["required_categories"].append("sse")
    path.write_text(json.dumps(raw))
    with pytest.raises(ManifestError, match="missing required categories"):
        load_manifest(path)


@pytest.mark.issue(737)
def test_repository_rejects_unreleased_chirp_dependency(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.1.0"\ndependencies=["bengal-chirp @ git+https://example.invalid/chirp"]\n'
    )
    manifest = load_manifest(_manifest(repo))
    with pytest.raises(ConformanceError, match="released Chirp"):
        validate_repository(manifest, repo)


@pytest.mark.issue(737)
def test_repository_rejects_runtime_pin_drift(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".python-version").write_text("3.13\n")
    manifest = load_manifest(_manifest(repo))
    with pytest.raises(ConformanceError, match="Python version"):
        validate_repository(manifest, repo)


@pytest.mark.issue(737)
def test_local_runner_waits_smokes_and_terminates(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest = load_manifest(_manifest(repo))
    report = run_local(manifest, repo, startup_timeout=10)
    assert [result.id for result in report.results] == ["home", "ready"]
    assert all(result.status == 200 for result in report.results)


@pytest.mark.issue(742)
def test_local_runner_generates_manifest_template_secrets(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest_path = _manifest(repo, required=["full-page"])
    raw = json.loads(manifest_path.read_text())
    raw["checks"][0]["contains"] = ["template-secret-set"]
    manifest_path.write_text(json.dumps(raw))

    report = run_local(load_manifest(manifest_path), repo, startup_timeout=10)

    assert [result.id for result in report.results] == ["home"]


@pytest.mark.issue(737)
def test_local_runner_uses_starter_venv_for_railway_python_command(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest_path = _manifest(repo)
    manifest_raw = json.loads(manifest_path.read_text())
    manifest_raw["template"]["start_command"] = "python app.py"
    manifest_path.write_text(json.dumps(manifest_raw))
    railway_path = repo / "railway.json"
    railway_raw = json.loads(railway_path.read_text())
    railway_raw["deploy"]["startCommand"] = "python app.py"
    railway_path.write_text(json.dumps(railway_raw))
    interpreter = repo / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    os.symlink(sys.executable, interpreter)

    report = run_local(load_manifest(manifest_path), repo, startup_timeout=10)

    assert [result.id for result in report.results] == ["home", "ready"]


@pytest.mark.issue(737)
def test_smoke_shares_cookies_and_extracted_values(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest_path = _manifest(repo, required=["full-page"])
    raw = json.loads(manifest_path.read_text())
    raw["checks"] = [
        {
            "id": "extract",
            "category": "full-page",
            "path": "/",
            "contains": ["hello"],
            "extract": {"word": "(hello)"},
        },
        {
            "id": "interpolate",
            "category": "full-page",
            "path": "/{{word}}",
            "contains": ["hello"],
        },
    ]
    manifest_path.write_text(json.dumps(raw))
    manifest = load_manifest(manifest_path)
    report = run_local(manifest, repo, startup_timeout=10)

    assert [result.id for result in report.results] == ["extract", "interpolate"]


@pytest.mark.issue(737)
def test_operation_receipt_requires_every_lifecycle_surface(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manifest = load_manifest(_manifest(repo))
    receipt_path = repo / "operations.json"
    receipt = {
        "template": "fixture",
        "source_ref": "abc123",
        "deployment_id": "deployment-123",
        "commit": "1234567890abcdef",
        "operations": {
            name: {"status": "passed", "evidence": f"proof for {name}"}
            for name in manifest.required_operations
        },
    }
    receipt_path.write_text(json.dumps(receipt))

    assert validate_operations(manifest, receipt_path) == receipt

    del receipt["operations"]["ejection"]
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ConformanceError, match=r"\[ejection\]"):
        validate_operations(manifest, receipt_path)
