#!/usr/bin/env python3
"""Build the GitHub Actions matrix for every published catalog starter."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_matrix(catalog_path: Path = ROOT / "catalog.json") -> dict[str, list[dict[str, str]]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    include = [
        {
            "slug": template["slug"],
            "repository": template["repository"],
            "ref": template["compatibility_ref"],
        }
        for template in catalog["templates"]
        if template["status"] == "published"
    ]
    return {"include": include}


if __name__ == "__main__":
    print(json.dumps(build_matrix(), separators=(",", ":")))
