"""Strict, dependency-free template manifest parsing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KNOWN_CATEGORIES = frozenset(
    {
        "asset",
        "form",
        "full-page",
        "health",
        "htmx",
        "oob",
        "readiness",
        "sse",
    }
)
KNOWN_OPERATIONS = frozenset(
    {"deployment", "ejection", "restart", "rollback", "shutdown", "update"}
)


class ManifestError(ValueError):
    """The template manifest is incomplete or contradictory."""


def _required_string(mapping: dict[str, Any], key: str, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{where}.{key} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class Variable:
    name: str
    source: str
    secret: bool


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    category: str
    method: str
    path: str
    status: int
    headers: tuple[tuple[str, str], ...]
    request_headers: tuple[tuple[str, str], ...]
    body: str | None
    contains: tuple[str, ...]
    extract: tuple[tuple[str, str], ...]
    stream: bool


@dataclass(frozen=True, slots=True)
class Manifest:
    path: Path
    slug: str
    title: str
    repository: str
    ref: str
    python: str
    chirp_spec: str
    chirp_locked: str
    start_command: str
    health_path: str
    owner: str
    support_url: str
    status: str
    public_url: str | None
    demo_url: str | None
    last_successful_smoke: str | None
    services: tuple[str, ...]
    variables: tuple[Variable, ...]
    required_categories: tuple[str, ...]
    checks: tuple[Check, ...]
    required_operations: tuple[str, ...]

    @property
    def required_user_variables(self) -> tuple[str, ...]:
        return tuple(variable.name for variable in self.variables if variable.source == "user")


def _parse_variables(raw: Any) -> tuple[Variable, ...]:
    if not isinstance(raw, list):
        raise ManifestError("template.variables must be a list")
    variables: list[Variable] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        where = f"template.variables[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{where} must be an object")
        name = _required_string(item, "name", where)
        if name in seen:
            raise ManifestError(f"duplicate variable {name!r}")
        seen.add(name)
        source = _required_string(item, "source", where)
        if source not in {"railway", "template", "user"}:
            raise ManifestError(f"{where}.source must be railway, template, or user")
        secret = item.get("secret", False)
        if not isinstance(secret, bool):
            raise ManifestError(f"{where}.secret must be a boolean")
        variables.append(Variable(name, source, secret))
    return tuple(variables)


def _string_pairs(raw: Any, where: str) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} must be an object")
    pairs: list[tuple[str, str]] = []
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ManifestError(f"{where} keys and values must be strings")
        pairs.append((key, value))
    return tuple(sorted(pairs))


def _parse_checks(raw: Any) -> tuple[Check, ...]:
    if not isinstance(raw, list) or not raw:
        raise ManifestError("checks must be a non-empty list")
    checks: list[Check] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        where = f"checks[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{where} must be an object")
        check_id = _required_string(item, "id", where)
        if check_id in seen:
            raise ManifestError(f"duplicate check id {check_id!r}")
        seen.add(check_id)
        category = _required_string(item, "category", where)
        if category not in KNOWN_CATEGORIES:
            raise ManifestError(f"{where}.category {category!r} is not recognized")
        method = str(item.get("method", "GET")).upper()
        path = _required_string(item, "path", where)
        if not path.startswith("/"):
            raise ManifestError(f"{where}.path must start with /")
        status = item.get("status", 200)
        if not isinstance(status, int) or not 100 <= status <= 599:
            raise ManifestError(f"{where}.status must be an HTTP status integer")
        body = item.get("body")
        if body is not None and not isinstance(body, str):
            raise ManifestError(f"{where}.body must be a string")
        contains = item.get("contains", [])
        if not isinstance(contains, list) or not all(isinstance(value, str) for value in contains):
            raise ManifestError(f"{where}.contains must be a string list")
        stream = item.get("stream", False)
        if not isinstance(stream, bool):
            raise ManifestError(f"{where}.stream must be a boolean")
        extract = _string_pairs(item.get("extract"), f"{where}.extract")
        for name, pattern in extract:
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                raise ManifestError(f"{where}.extract.{name} is not a valid regex") from exc
            if compiled.groups != 1:
                raise ManifestError(
                    f"{where}.extract.{name} must contain exactly one capture group"
                )
        checks.append(
            Check(
                id=check_id,
                category=category,
                method=method,
                path=path,
                status=status,
                headers=_string_pairs(item.get("headers"), f"{where}.headers"),
                request_headers=_string_pairs(
                    item.get("request_headers"), f"{where}.request_headers"
                ),
                body=body,
                contains=tuple(contains),
                extract=extract,
                stream=stream,
            )
        )
    return tuple(checks)


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a v1 template manifest."""

    manifest_path = Path(path).resolve()
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be an object")
    if raw.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    template = raw.get("template")
    if not isinstance(template, dict):
        raise ManifestError("template must be an object")
    repository = _required_string(template, "repository", "template")
    if not repository.startswith("https://github.com/"):
        raise ManifestError("template.repository must be a public GitHub HTTPS URL")
    health_path = _required_string(template, "health_path", "template")
    if not health_path.startswith("/"):
        raise ManifestError("template.health_path must start with /")
    services = template.get("services")
    if (
        not isinstance(services, list)
        or not services
        or not all(isinstance(service, str) and service for service in services)
    ):
        raise ManifestError("template.services must be a non-empty string list")
    checks = _parse_checks(raw.get("checks"))
    operations = raw.get("required_operations", sorted(KNOWN_OPERATIONS))
    if not isinstance(operations, list) or not all(isinstance(value, str) for value in operations):
        raise ManifestError("required_operations must be a string list")
    unknown_operations = set(operations) - KNOWN_OPERATIONS
    if unknown_operations:
        raise ManifestError(f"unknown required operations: {sorted(unknown_operations)}")
    required = raw.get("required_categories", sorted(KNOWN_CATEGORIES))
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        raise ManifestError("required_categories must be a string list")
    unknown_required = set(required) - KNOWN_CATEGORIES
    if unknown_required:
        raise ManifestError(f"unknown required categories: {sorted(unknown_required)}")
    present = {check.category for check in checks}
    missing = set(required) - present
    if missing:
        raise ManifestError(f"checks are missing required categories: {sorted(missing)}")
    status = _required_string(template, "status", "template")
    if status not in {"draft", "published"}:
        raise ManifestError("template.status must be draft or published")

    def optional_url(key: str) -> str | None:
        value = template.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("https://"):
            raise ManifestError(f"template.{key} must be null or an HTTPS URL")
        return value

    last_smoke = template.get("last_successful_smoke")
    if last_smoke is not None and (not isinstance(last_smoke, str) or not last_smoke.strip()):
        raise ManifestError("template.last_successful_smoke must be null or a timestamp")
    return Manifest(
        path=manifest_path,
        slug=_required_string(template, "slug", "template"),
        title=_required_string(template, "title", "template"),
        repository=repository,
        ref=_required_string(template, "ref", "template"),
        python=_required_string(template, "python", "template"),
        chirp_spec=_required_string(template, "chirp_spec", "template"),
        chirp_locked=_required_string(template, "chirp_locked", "template"),
        start_command=_required_string(template, "start_command", "template"),
        health_path=health_path,
        owner=_required_string(template, "owner", "template"),
        support_url=_required_string(template, "support_url", "template"),
        status=status,
        public_url=optional_url("public_url"),
        demo_url=optional_url("demo_url"),
        last_successful_smoke=last_smoke,
        services=tuple(services),
        variables=_parse_variables(template.get("variables")),
        required_categories=tuple(required),
        checks=checks,
        required_operations=tuple(operations),
    )
