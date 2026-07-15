from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
REQUIRED_FIELDS = {
    "slug",
    "title",
    "repository",
    "source_ref",
    "compatibility_ref",
    "owner",
    "support_url",
    "marketplace_url",
    "demo_url",
    "status",
    "chirp_spec",
    "chirp_locked",
    "last_successful_smoke",
    "update_status",
    "support_health",
}


def _catalog() -> dict[str, object]:
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


def test_catalog_exposes_maintainer_status_for_every_template() -> None:
    catalog = _catalog()
    templates = catalog["templates"]
    assert isinstance(templates, list)
    assert templates
    slugs = [template["slug"] for template in templates]
    assert len(slugs) == len(set(slugs))

    for template in templates:
        assert template.keys() >= REQUIRED_FIELDS
        assert template["status"] in {"draft", "published", "deprecated", "retired"}
        assert template["update_status"] in {"blocked", "reviewing", "compatible"}
        assert template["support_health"] in {"healthy", "degraded"}
        assert template["support_url"].startswith("https://")
        assert template["marketplace_url"].startswith("https://railway.com/deploy/")


def test_published_templates_have_smoke_and_operations_evidence() -> None:
    for template in _catalog()["templates"]:
        if template["status"] != "published":
            continue
        evidence = ROOT / "evidence" / template["slug"] / template["source_ref"]
        assert (evidence / "live-smoke.json").is_file()
        assert (evidence / "operations.json").is_file()


def test_compatibility_matrix_covers_every_published_template() -> None:
    completed = subprocess.run(  # noqa: S603 - bounded repository script
        [sys.executable, str(ROOT / "scripts" / "compatibility_matrix.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    matrix = json.loads(completed.stdout)
    expected = {
        template["slug"]
        for template in _catalog()["templates"]
        if template["status"] == "published"
    }
    assert {item["slug"] for item in matrix["include"]} == expected
