"""Command-line interface for template validation and smoke evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .manifest import ManifestError, load_manifest
from .runner import (
    ConformanceError,
    Report,
    report_dict,
    run_local,
    run_smoke,
    validate_operations,
    validate_repository,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chirp-railway-check")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate manifest and repository offline")
    validate.add_argument("manifest")
    validate.add_argument("--repo", default=".")

    local = subparsers.add_parser("local", help="start the production command and smoke it")
    local.add_argument("manifest")
    local.add_argument("--repo", default=".")
    local.add_argument("--port", type=int)
    local.add_argument("--startup-timeout", type=float, default=30.0)
    local.add_argument("--request-timeout", type=float, default=10.0)
    local.add_argument("--evidence")

    smoke = subparsers.add_parser("smoke", help="smoke an existing terminal deployment")
    smoke.add_argument("manifest")
    smoke.add_argument("--base-url", required=True)
    smoke.add_argument("--request-timeout", type=float, default=10.0)
    smoke.add_argument("--deployment-id")
    smoke.add_argument("--deployment-status")
    smoke.add_argument("--evidence")
    operations = subparsers.add_parser(
        "operations", help="validate restart/update/rollback/ejection evidence"
    )
    operations.add_argument("manifest")
    operations.add_argument("receipt")
    return parser


def _write_report(path: str | None, report: Report) -> None:
    payload = report_dict(report)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected conformance action."""

    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "validate":
            validate_repository(manifest, args.repo)
            print(f"valid: {manifest.slug}")
            return 0
        if args.command == "local":
            report = run_local(
                manifest,
                args.repo,
                port=args.port,
                startup_timeout=args.startup_timeout,
                request_timeout=args.request_timeout,
            )
            _write_report(args.evidence, report)
            return 0
        if args.command == "operations":
            validate_operations(manifest, args.receipt)
            print(f"operations valid: {manifest.slug}")
            return 0
        report = run_smoke(
            manifest,
            args.base_url,
            timeout=args.request_timeout,
            deployment_id=args.deployment_id,
            deployment_status=args.deployment_status,
        )
        _write_report(args.evidence, report)
        return 0
    except (ManifestError, ConformanceError, OSError, json.JSONDecodeError) as exc:
        print(f"conformance failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
